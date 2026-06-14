FROM dailyco/pipecat-base:latest

COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./bot.py bot.py
COPY ./prompts.py prompts.py
COPY ./tools.py tools.py
COPY ./sms.py sms.py
COPY ./db.py db.py
COPY ./webhooks.py webhooks.py
