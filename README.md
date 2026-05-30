# Transcript Evaluator

This project converts interview transcripts into evaluator-ready JSON, runs batch transcript evaluations in the browser, generates PDF reports, and experiments with agent-to-agent review flows.

## What Was Built

- A transcript converter that turns `INTERVIEWER` / `CANDIDATE` text into JSON cases.
- A browser evaluator that scores each case against behavioral and non-behavioral rubrics.
- A local reviewer-agent bridge at `http://localhost:8787/review`.
- Bright Data MCP integration for tool-backed second-agent experiments.
- A PDF feedback flow where Agent 2 sends a PDF report to Agent 1, and Agent 1 sends feedback back to Agent 2.
- A bias-review flow where Agent 1 reviews Agent 2's PDF report for possible evaluator bias.

## Main Files

- `txt_to_json.py` converts transcript `.txt` files into evaluator JSON.
- `evaluator.html` runs the browser UI.
- `web helpers/evaluator-app.js` coordinates batch evaluation, review calls, logging, and PDF generation.
- `web helpers/gemini.js` handles primary model calls and JSON repair.
- `web helpers/pdf.js` builds PDF reports from batch results.
- `agents/reviewer-agent.mjs` runs the local MCP-only reviewer bridge.
- `agents/pdf-feedback-flow.mjs` tests Agent 2 PDF handoff and Agent 1 feedback.
- `input data/entire_interview.txt` is the full source transcript.
- `input data/entire_interview.json` is the generated evaluator input.

## Setup

Create a local `.env` file. Do not commit it.

```env
GOOGLE_API_KEY=your_google_ai_studio_key
API_TOKEN=your_bright_data_api_token

MCP_MODE=stdio
MCP_COMMAND=npx
MCP_ARGS=["-y","@brightdata/mcp"]

PRO_MODE=true
GROUPS=browser,advanced_scraping,research
MCP_TOOL_NAME=extract

PDF_BIAS_TOOLS=web_data_chatgpt_ai_insights
PDF_BIAS_EXCERPT_CHARS=3500
PDF_BIAS_TOOL_TIMEOUT_MS=180000
```

`web helpers/config.js` may also define `window.GEMINI_API_KEY` for the browser UI. It is ignored by git.

## Convert Transcript

```powershell
python txt_to_json.py "input data\entire_interview.txt" --workers 8
```

Expected output:

- `input data/entire_interview.json`
- `log/entire_interview_entry_timing.log`

## Run Reviewer Agent

```powershell
npm run review-agent
```

Health check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8787/health
```

List MCP tools:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8787/tools
```

The reviewer agent is MCP-only. It does not fall back to Gemini.

## Run Browser Evaluator

Serve the repo locally, then open `evaluator.html`.

```powershell
python -m http.server 8000 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8000/evaluator.html?batchSize=6&file=input%20data/entire_interview.json
```

## Agent Message Tests

### Agent 2 sends PDF to Agent 1

```powershell
npm run pdf-feedback
```

The script:

1. Finds the latest `evaluation_report_*.pdf`.
2. Builds an Agent 2 message containing the PDF path, filename, byte size, and SHA-256.
3. Extracts text from the PDF.
4. Has Agent 1 return feedback to Agent 2.

### Bias Review

The latest flow asks Agent 1 to review whether Agent 2's report appears biased based on the PDF text.

It ignores whether the PDF has a dedicated `Second Agent Review` section and instead uses the configured Bright Data AI insight tools.

Default:

```env
PDF_BIAS_TOOLS=web_data_chatgpt_ai_insights
```

Optional slower comparison:

```env
PDF_BIAS_TOOLS=web_data_chatgpt_ai_insights,web_data_perplexity_ai_insights,web_data_grok_ai_insights
```

Grok and Perplexity can be slow because Bright Data runs them as async snapshot jobs.

## Bright Data MCP Tools

The enabled Bright Data MCP setup exposes tools such as:

- `search_engine`
- `search_engine_batch`
- `scrape_as_markdown`
- `scrape_as_html`
- `scrape_batch`
- `extract`
- `session_stats`
- `web_data_chatgpt_ai_insights`
- `web_data_grok_ai_insights`
- `web_data_perplexity_ai_insights`
- `web_data_github_repository_file`
- `web_data_reuter_news`
- browser tools like `scraping_browser_navigate`, `scraping_browser_snapshot`, `scraping_browser_click_ref`, `scraping_browser_type_ref`, and `scraping_browser_screenshot`

## Notes From Testing

- `entire_interview.txt` converted successfully into 23 JSON cases.
- The original reviewer default model `gemini-3.1-lite` was unavailable through the Gemini API.
- The reviewer bridge was changed to MCP-only.
- Bright Data MCP initially exposed only search/scrape tools until `PRO_MODE`, `GROUPS`, and `TOOLS` were configured.
- `search_engine` worked but returns search results, not evaluator judgments.
- `extract` requires a URL and can time out for long prompts.
- `session_stats` confirmed the MCP connection works.
- AI insight tools work as async Bright Data snapshot jobs and may take more than two minutes.

## Safety

Do not commit:

- `.env`
- `web helpers/config.js`
- API keys or Bright Data tokens

Both `.env` and `config.js` are gitignored.
