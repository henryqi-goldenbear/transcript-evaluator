# Transcript Evaluator

Transcript Evaluator converts interview transcripts into structured cases, scores each candidate answer with Mistral, writes detailed evaluation logs, and hands the finished run to Agent 2 for a final QA report.

## What This Does

The project has four main pieces:

- **Frontend:** `evaluator.html` and the files in `web helpers/`.
- **Backend:** `txt_to_json.py`, which converts transcripts, serves the local API, writes logs, and proxies Mistral calls.
- **Agent 1 / evaluator workflow:** the converter plus frontend evaluator that scores each interview case.
- **Agent 2 / reviewer workflow:** `agent2_connection.py` queues the finished evaluation payload and `agent2.py` sends it to the configured Mistral Agent for a final report.

## How The Workflow Runs

1. A `.txt` transcript from `input data/` is passed to `txt_to_json.py`.
2. `txt_to_json.py` parses interviewer/candidate turns into evaluator-ready JSON.
3. The script starts the local pipeline server on port `3000` and opens `evaluator.html`.
4. The frontend loads the generated JSON, rubric files from `docs/`, and the selected Mistral model.
5. Each case is sent to the backend endpoint `/mistral/evaluate`.
6. The backend calls Mistral through `https://api.mistral.ai/v1/chat/completions`.
7. The frontend parses the JSON score response, displays results, and appends detailed scoring breakdowns to `logs/{file}_eval.log`.
8. When the batch completes, the frontend calls `/agent2/handoff`.
9. `agent2_connection.py` packages the evaluation log, original transcript, and generated JSON into a websocket payload.
10. `agent2.py` receives that payload, calls the configured Mistral Agent, and writes the final report under `logs/agent2/`.

Final Agent 2 reports are named like:

```text
logs/agent2/agent2_entire_interview_truncated_06-06-26.md
```

The date inside the report header is written as `MM/DD/YY`.

## Frontend

The frontend is intentionally simple: static HTML plus browser helper scripts.

- `evaluator.html` is the main evaluator UI.
- `web helpers/mistral.js` sends evaluation requests to the local backend.
- `web helpers/evaluator-app.js` manages batches, scoring output, follow-up handling, PDF/export data, and Agent 2 handoff.
- `web helpers/log.js` writes browser-side evaluation progress back to the backend log endpoint.
- `web helpers/pdf.js` builds report exports.
- `web helpers/rubrics.js` loads behavioral and non-behavioral rubric text.
- `web helpers/analytics.js` records request attempts, retries, failures, and debug traces.

The frontend does not call Mistral directly. It calls the local backend so API keys stay out of browser code.

## Backend

`txt_to_json.py` does three jobs:

- Converts transcript text into structured JSON cases.
- Runs the local pipeline server with `ThreadingHTTPServer`.
- Exposes local endpoints for logs, Mistral evaluation, and Agent 2 handoff.

Important endpoints:

```text
GET  /pipeline-log/health
POST /pipeline-log
POST /mistral/evaluate
POST /agent2/handoff
GET  /agent2-ws
```

By default, evaluation uses:

```text
mistral-small-latest
```

You can override it with:

```text
MISTRAL_EVALUATOR_MODEL=mistral-large-latest
```

## Two-Agent Flow

Agent 1 is the evaluator pipeline. It converts the transcript, scores each case, writes scoring details, and decides when the run is finished.

Agent 2 is the reviewer. It receives the full context from Agent 1:

- the original transcript text
- the generated evaluator JSON
- the detailed evaluation log

The bridge between them is `agent2_connection.py`. The frontend posts to `/agent2/handoff`, the backend queues a payload, and `agent2.py` connects back over `/agent2-ws` to receive that payload. Agent 2 then calls the Mistral Agent configured by:

```text
MISTRAL_AGENT2_ID
MISTRAL_AGENT2_VERSION
```

If those are not set, `agent2.py` uses the default Agent 2 ID already configured in the script.

## Gemini To Mistral Change

The evaluator previously used the Gemini path. The current workflow has been moved to Mistral end to end:

- evaluator calls now go through `/mistral/evaluate`
- the UI only exposes Mistral model choices
- the default model is `mistral-small-latest`
- Agent 2 also calls Mistral
- old Gemini browser prompts and helper code were removed from the active workflow

In this project, switching from the old Gemini workflow to Mistral improved practical evaluation speed by roughly **50-60x**. The biggest wins came from:

- using `mistral-small-latest` as the default model
- routing requests through one local backend instead of browser-side provider logic
- using Mistral JSON response mode for cleaner structured output
- reducing retry/format-repair overhead
- keeping the whole pipeline on one provider instead of mixing Gemini and Mistral paths

The result is a faster, simpler workflow with fewer stale prompts and fewer provider-specific branches.

## Setup

Create or update `.env` with:

```text
MISTRAL_API_KEY=your_mistral_api_key
MISTRAL_EVALUATOR_MODEL=mistral-small-latest
MISTRAL_AGENT2_ID=ag_019e9f09fadc72f7b26c3a4eace4fcd1
MISTRAL_AGENT2_VERSION=1
```

`MISTRAL_EVALUATOR_MODEL` is optional because the backend already defaults to `mistral-small-latest`.

## Run The Evaluator

From the project root:

```powershell
python txt_to_json.py "input data/entire_interview_truncated.txt" --batch-size 3
```

This writes:

```text
input data/entire_interview_truncated.json
logs/entire_interview_truncated_eval.log
```

It also opens the evaluator in the browser.

In VS Code, you can use:

```text
Convert and Run Evaluator
```

or open the evaluator directly with:

```text
Open Evaluator
```

## Run The Test Runner

In VS Code, run:

```text
Run Test Runner
```

That regenerates `tests/test_cases.json`, starts the local pipeline server, and opens:

```text
http://localhost:3000/tests/test_runner.html?v=mistral-small-1
```

## Outputs

Primary outputs:

- `input data/*.json`: parsed transcript cases
- `logs/*_eval.log`: evaluator logs with scoring breakdowns
- `logs/agent2/agent2_{file_name}_{MM-DD-YY}.md`: final Agent 2 QA reports
- `reports/`: exported reports and supporting artifacts

All runtime time marks are local `HH:MM:SS`.

## Follow-Up Steps

Good next improvements:

- Add a timing benchmark log that records total runtime, per-case runtime, and model used for every batch.
- Add a small dashboard that compares Mistral Small vs Mistral Large on speed, score stability, and JSON validity.
- Add automated regression tests for a few known transcripts so prompt changes do not silently change scoring.
- Add a "rerun failed cases only" button in the frontend.
- Add a config panel for Agent 2 so the agent ID/version can be changed without editing `.env`.
- Add a final report index page that lists every `logs/agent2/*.md` report by transcript name and date.
- Move the remaining optional Ollama classification path behind an explicit setting if you want the project to be fully Mistral-only.

