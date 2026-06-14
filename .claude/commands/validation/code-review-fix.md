# Code Review Fix - Address Review Issues

Fix issues identified in a code review.

## Instructions

### Input
Review file path: $ARGUMENTS (or latest review in `.agents/code-reviews/`)

### Process

1. **Load Review**
   - Read review from `.agents/code-reviews/`
   - Parse issues list

2. **Fix Issues**
   For each issue marked:
   - Announce fix being applied
   - Make the change
   - Mark issue resolved

3. **Re-validate**
   Run `/validate` after fixes

4. **Update Review File**
   Mark issues as fixed in review document

### Output
Summary of fixes applied and remaining issues (if any).

## Usage
```
/code-review-fix
/code-review-fix .agents/code-reviews/2026-06-14-main.md
```
