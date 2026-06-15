"""Summit Realty Group demo voice agent.

Browser-based demo using Pipecat's dev runner (WebRTC transport + prebuilt UI)
and a cascade voice pipeline: Deepgram Flux STT, OpenAI Chat LLM, and Cartesia TTS.

Run with:

    python bot.py

Then open http://localhost:7860/client and allow microphone access.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from db import audio_to_wav, log_call, upload_recording
from prompts import SYSTEM_INSTRUCTION
from tools import (
    alert_agent,
    book_appointment,
    capture_lead,
    check_area,
    check_availability,
    qualify_lead,
    send_confirmation_sms,
    transfer_to_human,
)

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    FunctionCallResultFrame,
    LLMRunFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import RunnerArguments, WebSocketRunnerArguments
from pipecat.runner.utils import (
    _create_telephony_transport,
    _get_transport_params,
    create_transport,
    parse_telephony_websocket,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies
from pipecat.workers.runner import WorkerRunner

import webhooks  # noqa: F401  (registers /webhooks/tally and /twiml/outbound routes)

load_dotenv(override=True)

_file_logging_configured = False


def _ensure_file_logging():
    """Add the DEBUG file sink, once per process.

    Must happen lazily (not at module import time): pipecat's runner `main()`
    calls `logger.remove()` during startup, which would strip a sink added at
    import time before the server ever starts.
    """
    global _file_logging_configured
    if _file_logging_configured:
        return
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    logger.add(
        logs_dir / "bot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="14 days",
    )
    _file_logging_configured = True


def _build_krisp_filter():
    """Return a KrispVivaFilter if KRISP_VIVA_* env vars are configured, else None.

    Krisp is fully optional: with no env vars set, this returns None and the demo
    runs without it.
    """
    model_path = os.environ.get("KRISP_VIVA_FILTER_MODEL_PATH") or os.environ.get(
        "KRISP_VIVA_MODEL_PATH"
    )
    api_key = os.environ.get("KRISP_VIVA_API_KEY")
    if not (model_path and api_key):
        return None

    try:
        from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter

        return KrispVivaFilter(model_path=model_path, api_key=api_key)
    except ImportError:
        logger.warning(
            "KRISP_VIVA_* env vars set but krisp_audio package isn't installed; "
            "skipping Krisp noise cancellation"
        )
        return None


def _cartesia_text_aggregation_mode() -> TextAggregationMode:
    mode = os.environ.get("CARTESIA_TEXT_AGGREGATION", "token").strip().lower()
    if mode == "sentence":
        return TextAggregationMode.SENTENCE
    if mode != "token":
        logger.warning(
            f"Unsupported CARTESIA_TEXT_AGGREGATION={mode!r}; using token aggregation"
        )
    return TextAggregationMode.TOKEN


transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_filter=_build_krisp_filter(),
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_filter=_build_krisp_filter(),
    ),
}


class CallSummaryObserver(BaseObserver):
    """Accumulates lead/qualification/booking details and the transcript from a call
    for end-of-call logging."""

    def __init__(self, stt, tts):
        super().__init__()
        self.summary: dict = {}
        self._transcript_chunks: list[tuple[str, str]] = []
        self._stt = stt
        self._tts = tts

    @property
    def transcript_lines(self) -> list[str]:
        """Merge consecutive same-speaker chunks into one line per turn."""
        lines: list[str] = []
        for speaker, text in self._transcript_chunks:
            if lines and lines[-1].startswith(f"{speaker}:"):
                lines[-1] += text
            else:
                lines.append(f"{speaker}:{text}")
        return lines

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame

        # TranscriptionFrame/TTSTextFrame originate at provider services and are then
        # re-pushed through several downstream processors, firing on_push_frame once
        # per hop. Only capture at the origin to avoid duplicate transcript lines.
        if isinstance(frame, TranscriptionFrame) and data.source is self._stt:
            self._transcript_chunks.append(("Caller", f" {frame.text}"))
            return
        if isinstance(frame, TTSTextFrame) and data.source is self._tts:
            self._transcript_chunks.append(("Ava", frame.text))
            return

        if not isinstance(frame, FunctionCallResultFrame):
            return

        args = frame.arguments or {}
        result = frame.result or {}

        if frame.function_name == "capture_lead":
            self.summary.update(
                lead_phone=args.get("phone"),
                lead_name=args.get("name"),
                lead_type=args.get("lead_type"),
            )
            if args.get("reason"):
                self.summary["notes"] = args["reason"]
        elif frame.function_name == "qualify_lead":
            self.summary.update(
                timeline=args.get("timeline"),
                area=args.get("area"),
                price_range=args.get("price_range"),
                pre_approved=args.get("pre_approved"),
                property_needs=args.get("property_needs"),
                seller_address=args.get("seller_address"),
            )
        elif frame.function_name == "book_appointment":
            self.summary.update(
                lead_name=args.get("name"),
                lead_phone=args.get("phone"),
                appointment_type=args.get("appointment_type"),
                appointment_time=args.get("appointment_time"),
                booking_id=result.get("booking_id"),
            )
            if args.get("notes"):
                self.summary["notes"] = args["notes"]
        elif frame.function_name == "alert_agent":
            self.summary.update(
                lead_name=args.get("name"),
                lead_phone=args.get("phone"),
                hot_lead=True,
                notes=args.get("reason"),
            )
            if args.get("area"):
                self.summary["area"] = args["area"]


class ToolResultPushFix(BaseObserver):
    """Works around a pipecat bug where a function-call result that arrives while
    the user is (briefly) flagged as speaking never gets pushed to the LLM,
    leaving the bot silent until an unrelated later turn happens to flush it.

    LLMAssistantAggregator only pushes the context frame containing the tool
    result when `not self._user_speaking` at the moment the result arrives, and
    has no deferred-retry for the user-speaking case (unlike its bot-speaking
    equivalent). If we see that race, push the context frame ourselves once the
    user finishes speaking.
    """

    def __init__(self, assistant_aggregator):
        super().__init__()
        self._assistant_aggregator = assistant_aggregator
        self._pending_tool_results: set[str] = set()
        self._flush_task: asyncio.Task | None = None

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if not isinstance(frame, FunctionCallResultFrame):
            return

        # Observers see each frame at every pipeline hop. Only react when the
        # result is being delivered to the assistant aggregator, otherwise one
        # tool result can trigger several duplicate LLM runs.
        if data.destination is not self._assistant_aggregator:
            return

        if frame.tool_call_id in self._pending_tool_results:
            return

        self._pending_tool_results.add(frame.tool_call_id)
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_when_safe())

    async def _flush_when_safe(self):
        # Let LLMAssistantAggregator handle the FunctionCallResultFrame first.
        await asyncio.sleep(0.05)

        if not getattr(self._assistant_aggregator, "_user_speaking", False):
            self._pending_tool_results.clear()
            return

        max_wait_secs = float(os.environ.get("TOOL_RESULT_FLUSH_MAX_WAIT_SECS", "1.2"))
        deadline = asyncio.get_running_loop().time() + max_wait_secs
        while (
            getattr(self._assistant_aggregator, "_user_speaking", False)
            and asyncio.get_running_loop().time() < deadline
        ):
            await asyncio.sleep(0.05)

        pending = ", ".join(sorted(self._pending_tool_results))
        if getattr(self._assistant_aggregator, "_user_speaking", False):
            logger.warning(
                f"ToolResultPushFix: forcing context push after {max_wait_secs:.1f}s "
                f"with user still marked speaking; tool_call_ids={pending}"
            )
        else:
            logger.debug(f"ToolResultPushFix: flushing deferred tool results; tool_call_ids={pending}")

        self._pending_tool_results.clear()
        await self._assistant_aggregator.push_context_frame(FrameDirection.UPSTREAM)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, call_data: dict | None = None):
    _ensure_file_logging()
    logger.info("Starting Ava (Summit Realty Group demo)")

    deepgram_model = os.environ.get("DEEPGRAM_MODEL", "flux-general-en")
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    cartesia_model = os.environ.get("CARTESIA_MODEL", "sonic-3.5")
    cartesia_text_aggregation = _cartesia_text_aggregation_mode()

    stt = DeepgramFluxSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramFluxSTTService.Settings(
            model=deepgram_model,
            eager_eot_threshold=float(os.environ.get("DEEPGRAM_EAGER_EOT_THRESHOLD", "0.5")),
            eot_threshold=float(os.environ.get("DEEPGRAM_EOT_THRESHOLD", "0.8")),
        ),
    )
    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            model=openai_model,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.3")),
            max_completion_tokens=int(os.environ.get("OPENAI_MAX_COMPLETION_TOKENS", "180")),
        ),
    )
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        text_aggregation_mode=cartesia_text_aggregation,
        settings=CartesiaTTSService.Settings(
            model=cartesia_model,
            voice=os.environ["CARTESIA_VOICE_ID"],
        ),
    )
    logger.info(
        "Voice pipeline configured: "
        f"Deepgram={deepgram_model}, OpenAI={openai_model}, "
        f"Cartesia={cartesia_model}, Cartesia aggregation={cartesia_text_aggregation.value}"
    )

    for tool_fn in (
        check_area,
        check_availability,
        book_appointment,
        alert_agent,
        capture_lead,
        qualify_lead,
        transfer_to_human,
        send_confirmation_sms,
    ):
        llm.register_direct_function(tool_fn)

    context = LLMContext(
        tools=ToolsSchema(
            standard_tools=[
                check_area,
                check_availability,
                book_appointment,
                alert_agent,
                capture_lead,
                qualify_lead,
                transfer_to_human,
                send_confirmation_sms,
            ]
        )
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=ExternalUserTurnStrategies(),
        ),
    )

    audio_buffer = AudioBufferProcessor(num_channels=2)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            audio_buffer,
            assistant_aggregator,
        ]
    )

    call_summary_observer = CallSummaryObserver(stt, tts)
    tool_result_push_fix = ToolResultPushFix(assistant_aggregator)

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[TranscriptionLogObserver(), call_summary_observer, tool_result_push_fix],
    )

    recorded_audio: dict = {}

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        logger.debug(f"on_audio_data fired: {len(audio)} bytes, sample_rate={sample_rate}, channels={num_channels}")
        recorded_audio["audio"] = audio
        recorded_audio["sample_rate"] = sample_rate
        recorded_audio["num_channels"] = num_channels

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        await audio_buffer.start_recording()
        logger.debug(f"audio_buffer recording started, sample_rate={audio_buffer.sample_rate}")
        call_body = (call_data or {}).get("body") or {}
        if call_body.get("call_type") == "outbound_demo":
            lead_name = call_body.get("lead_name", "there")
            context.add_message(
                {
                    "role": "developer",
                    "content": (
                        f"This is an outbound demo call you placed to {lead_name}. "
                        f"Greet them by name as described for outbound demo calls now."
                    ),
                }
            )
        else:
            context.add_message(
                {"role": "developer", "content": "Greet the caller with your opening line now."}
            )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        logger.debug(
            f"Before stop_recording: user_buffer={len(audio_buffer._user_audio_buffer)} bytes, "
            f"bot_buffer={len(audio_buffer._bot_audio_buffer)} bytes, "
            f"sample_rate={audio_buffer.sample_rate}, recording={audio_buffer._recording}"
        )
        await audio_buffer.stop_recording()
        logger.debug(f"recorded_audio after stop: {bool(recorded_audio.get('audio'))}")
        if call_summary_observer.summary or call_summary_observer.transcript_lines:
            summary = dict(call_summary_observer.summary)
            if call_summary_observer.transcript_lines:
                summary["transcript"] = "\n".join(call_summary_observer.transcript_lines)
            if recorded_audio.get("audio"):
                wav_bytes = audio_to_wav(
                    recorded_audio["audio"],
                    recorded_audio["sample_rate"],
                    recorded_audio["num_channels"],
                )
                recording = upload_recording(wav_bytes)
                if recording.get("url"):
                    summary["recording_url"] = recording["url"]
            log_call(summary)
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    call_data = None
    if isinstance(runner_args, WebSocketRunnerArguments) and runner_args.transport_type is None:
        # Telephony connection (e.g. Twilio media stream). parse_telephony_websocket()
        # consumes messages from the stream and isn't idempotent, so we parse once here
        # and build the transport directly instead of calling create_transport() (which
        # would parse again and consume the stream a second time).
        transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
        params = _get_transport_params(transport_type, transport_params)
        transport = await _create_telephony_transport(
            runner_args.websocket, params, transport_type, call_data
        )
    else:
        transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args, call_data)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
