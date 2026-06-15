# Transcript Evaluator

Transcript Evaluator converts interview transcripts into structured cases, scores each candidate answer with Mistral, writes detailed evaluation logs, and hands the finished run to Agent 2 for a final QA report.

## What This Does

The project has five main pieces:

- **Frontend:** `src/frontend/evaluator.html` and the files in `src/frontend/web_helpers/`.
- **Agent 1 / backend:** `src/agent1/txt_to_json.py`, which converts transcripts, serves the local API, writes logs, and proxies Mistral calls.
- **Agent 1 / evaluator workflow:** the converter plus frontend evaluator that scores each interview case.
- **Classifier agent:** a lightweight Ministral agent inside `src/agent1/txt_to_json.py` that categorizes transcript turns before scoring.
- **Agent 2 / reviewer workflow:** `src/bridge/agent2_connection.py` queues the finished evaluation payload and `src/agent2/agent2.py` sends it to the configured Mistral Agent for a final report.

## How The Workflow Runs

1. A `.txt` transcript from `input data/` is passed to Agent 0 in `src/agent1/txt_to_json.py`.
2. Agent 0 drafts evaluator-ready JSON. By default, a small Ministral classifier categorizes turns as behavioral, non-behavioral, non-question, follow-up, clarifying, or deepening.
3. Before scoring starts, Agent 0 sends a compact transcript/case outline to Agent 2 for structure review.
4. Agent 2 either approves the structure or returns compact correction operations, such as splitting a follow-up into a new case, adding a missing case, moving a follow-up, or changing a probe type.
5. Agent 0 applies those operations locally and resubmits the compact outline until Agent 2 is satisfied. If Agent 2 repeatedly fails to return usable JSON or usable operations, the run stops with a clear log path instead of silently accepting a bad structure.
6. Agent 0 writes the approved JSON, starts the local pipeline server on port `3000`, and opens `src/frontend/evaluator.html`.
7. Agent 1, the frontend evaluator, loads the approved JSON, rubric files from `docs/`, and the selected Mistral model.
8. Each case is sent to the backend endpoint `/mistral/evaluate`.
9. The backend calls Mistral through `https://api.mistral.ai/v1/chat/completions`.
10. The frontend parses the JSON rating response, displays results, appends detailed breakdowns to `logs/agent1/{file}/{file}_eval.log`, and writes result records to `logs/agent1/{file}/{file}.log`.
11. When the batch completes, the frontend calls `/agent2/handoff`.
12. `src/bridge/agent2_connection.py` packages the evaluation log, original transcript, and approved JSON into a websocket payload.
13. `src/agent2/agent2.py` receives that payload, calls the configured Mistral Agent, and writes the final report under `logs/agent2/{file}/`.

Final Agent 2 reports are named like:

```text
logs/agent2/entire_interview_truncated/agent2_entire_interview_truncated_06-06-26.md
```

The report header includes a local timestamp and a `MM/DD/YY` date.

## Frontend

The frontend is intentionally simple: static HTML plus browser helper scripts.

- `src/frontend/evaluator.html` is the main evaluator UI.
- `src/frontend/web_helpers/mistral.js` sends evaluation requests to the local backend.
- `src/frontend/web_helpers/evaluator-app.js` manages batches, scoring output, follow-up handling, PDF/export data, and Agent 2 handoff.
- `src/frontend/web_helpers/log.js` writes browser-side evaluation progress back to the backend log endpoint.
- `src/frontend/web_helpers/pdf.js` builds report exports.
- `src/frontend/web_helpers/rubrics.js` defines the unified scoring rubric.
- `src/frontend/web_helpers/analytics.js` records request attempts, retries, failures, and debug traces.

The frontend does not call Mistral directly. It calls the local backend so API keys stay out of browser code.

## Backend

`src/agent1/txt_to_json.py` acts as Agent 0 and does four jobs:

- Converts transcript text into structured JSON cases.
- Runs the Agent 2 structure-review loop before scoring.
- Runs the local pipeline server with `ThreadingHTTPServer`.
- Exposes local endpoints for logs, Mistral evaluation, and Agent 2 handoff.

The transcript conversion step uses a separate lightweight classifier agent so the main evaluator model does not spend tokens on low-reasoning categorization. The default classifier is:

```text
ministral-3b-latest
```

You can override it with:

```text
MISTRAL_CLASSIFIER_MODEL=ministral-8b-latest
```

You can also bypass the classifier agent:

```powershell
python -m src.agent1.txt_to_json "input data/entire_interview_truncated.txt" --classifier-provider heuristic
```

By default, Agent 0 keeps looping with Agent 2 until Agent 2 approves the structure.

You can bypass the Agent 2 pre-evaluation structure loop when debugging:

```powershell
python -m src.agent1.txt_to_json "input data/entire_interview_truncated.txt" --structure-review-iterations 0
```

You can also set a manual cap if you want the loop to stop after a fixed number of attempts:

```text
AGENT2_STRUCTURE_REVIEW_ITERATIONS=5
```

Use `-1` for the default "until satisfied" behavior, `0` to skip, or a positive number to cap attempts.

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

Agent 2 audits both rating quality and Agent 1's transcript structure. It checks whether main
questions were split correctly, whether non-scorable turns were skipped, whether follow-ups were
attached to the right parent case, and whether each follow-up probe is correctly labeled as
clarifying or deepening. When it finds a structure issue, it should pinpoint the case, question,
nearby transcript context, and the correction needed in `txt_to_json.py`.

The bridge between them is `src/bridge/agent2_connection.py`. The frontend posts to `/agent2/handoff`, the backend queues a payload, and `src/agent2/agent2.py` connects back over `/agent2-ws` to receive that payload. Agent 2 then calls the Mistral Agent configured by:

```text
MISTRAL_AGENT2_ID
MISTRAL_AGENT2_VERSION
```

If those are not set, `src/agent2/agent2.py` uses the default Agent 2 ID already configured in the script.

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
MISTRAL_CLASSIFIER_MODEL=ministral-3b-latest
MISTRAL_EVALUATOR_MODEL=mistral-small-latest
MISTRAL_AGENT2_ID=ag_019e9f09fadc72f7b26c3a4eace4fcd1
MISTRAL_AGENT2_VERSION=1
```

`MISTRAL_EVALUATOR_MODEL` is optional because the backend already defaults to `mistral-small-latest`.

## Run The Evaluator

From the project root:

```powershell
python -m src.agent1.txt_to_json "input data/entire_interview_truncated.txt" --batch-size 3
```

This writes:

```text
input data/entire_interview_truncated.json
logs/entry_timing/entire_interview_truncated_entry_timing.log
logs/agent1/entire_interview_truncated/entire_interview_truncated_eval.log
logs/agent1/entire_interview_truncated/entire_interview_truncated.log
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
http://localhost:3000/tests/test_runner.html?v=mistral-small-4
```

## Outputs

Primary outputs:

- `input data/*.json`: parsed transcript cases
- `logs/entry_timing/{file}_entry_timing.log`: Agent 1 conversion and per-entry timing logs
- `logs/agent1/{file}/{file}_eval.log`: evaluator logs with scoring breakdowns
- `logs/agent1/{file}/{file}.log`: structured evaluator result records
- `logs/agent2/{file}/agent2_{file}_{MM-DD-YY}.md`: final Agent 2 QA reports
- `reports/`: exported reports and supporting artifacts

All runtime time marks are local `HH:MM:SS`.

To erase all log files and keep the log folders ready for the next run:

```text
python -m src.agent1.txt_to_json clean
```

## Follow-Up Steps

Good next improvements:

- Add a timing benchmark log that records total runtime, per-case runtime, and model used for every batch.
- Add a small dashboard that compares Mistral Small vs Mistral Large on speed, score stability, and JSON validity.
- Add automated regression tests for a few known transcripts so prompt changes do not silently change scoring.
- Add a "rerun failed cases only" button in the frontend.
- Add a config panel for Agent 2 so the agent ID/version can be changed without editing `.env`.
- Add a final report index page that lists every `logs/agent2/{file}/*.md` report by transcript name and date.
- Move the remaining optional Ollama classification path behind an explicit setting if you want the project to be fully Mistral-only.

