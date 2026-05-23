# API Rate Limits Reference

> Assumptions: ~1,000 tokens/request, 22 cases per full run.

---

## Groq (Free Tier)

| Model | TPD | Runs/day (TPD) | RPD | Runs/day (RPD) | TPM | Delay needed | Runs/min (TPM) |
|---|---|---|---|---|---|---|---|
| `llama-3.1-8b-instant` | 500,000 | 22 | 14,400 | 654 | 6,000 | 10,000 ms | 2.7 |
| `llama-4-scout-17b` | 500,000 | 22 | 1,000 | 45 | 30,000 | 2,000 ms | 13.6 |
| `qwen/qwen3-32b` | 500,000 | 22 | 1,000 | 45 | 6,000 | 10,000 ms | 2.7 |
| `openai/gpt-oss-20b` | 200,000 | 9 | 1,000 | 45 | 8,000 | 7,500 ms | 3.6 |
| `openai/gpt-oss-120b` | 200,000 | 9 | 1,000 | 45 | 8,000 | 7,500 ms | 3.6 |
| `llama-3.3-70b-versatile` | 100,000 | 4 | 1,000 | 45 | 12,000 | 5,000 ms | 5.5 |

**Bottleneck:** TPD in every case. RPD only matters for `llama-3.1-8b-instant`.

---

## Google AI Studio (Free Tier)

| Model | RPM | RPD | TPM | TPD | Runs/day (TPD) | Delay needed | Notes |
|---|---|---|---|---|---|---|---|
| Gemini 2.0 Flash | 15 | 1,500 | 1,000,000 | 15,000,000 | 681 | 4,000 ms | Best throughput |
| Gemini 2.5 Flash | 10 | 1,500 | 250,000 | 15,000,000 | 681 | 6,000 ms | Better quality |
| Gemini 2.5 Pro | 5 | 50 | 150,000 | 1,500,000 | 45 | 12,000 ms | Final validation only |

---

## Cerebras (Free Tier)

| Model | RPM | TPM | TPD | Runs/day (TPD) | Delay needed | Notes |
|---|---|---|---|---|---|---|
| `gpt-oss-120b` | 5 | 30,000 | 1,000,000 | 45 | 12,000 ms | Very generous TPD |
| `llama3.1-8b` | 5 | 30,000 | 1,000,000 | 45 | 12,000 ms | Fast inference |

**Note:** Free tier context window capped at 8,192 tokens.

---

## Cohere (Trial Key)

| Model | RPM | Monthly cap | Runs/month | Notes |
|---|---|---|---|---|
| Command R / R+ | 20 | 1,000 calls/month | ~45 total | Not useful for iteration |

---

## Summary — Best Options by Use Case

| Use case | Model | Service | Delay | Runs/day |
|---|---|---|---|---|
| Prompt iteration (speed) | Gemini 2.0 Flash | Google AI Studio | 4,000 ms | 681 |
| Prompt iteration (quality) | Gemini 2.5 Flash | Google AI Studio | 6,000 ms | 681 |
| Quality validation | Gemini 2.5 Pro | Google AI Studio | 12,000 ms | 50 |
| Free high-volume backup | llama-4-scout-17b | Groq | 2,000 ms | 22 |
| Final benchmark | GPT-5-Mini | Puter / OpenRouter | 1,500 ms | paid |
