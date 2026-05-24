# Non-Behavioral Interview Evaluation Rubric

Use this rubric for prompts that are not strict STAR behavioral questions, such as:
- "Tell me about yourself"
- "What are your weaknesses?"
- "Why do you want this role?"
- "Walk me through your resume"
- "How have you used <skill>?"

## Scoring Dimensions

### 1. Clarity (1-5)
- **5**: Clean structure, concise language, easy to follow from start to finish
- **4**: Mostly clear with minor roughness
- **3**: Understandable but loose structure or mild filler
- **2**: Hard to follow, vague enough to obscure key points
- **1**: Incoherent or non-answer

### 2. Relevance (1-5)
- **5**: Directly answers the specific question and is role/company aligned
- **4**: Mostly on-topic; limited generic phrasing
- **3**: Partly on-topic but includes substantial generic content
- **2**: Nominally related, largely generic and reusable anywhere
- **1**: Does not answer the question asked

### 3. Specificity (1-5)
- **5**: Concrete details: companies, projects, timelines, tools, metrics
- **4**: Mostly concrete with minor gaps
- **3**: Mix of concrete and abstract statements
- **2**: Mostly abstract with very few specifics
- **1**: Entirely abstract / platitudinous

### 4. Self-Awareness (1-5, only when applicable)
Apply only for introspective prompts (weaknesses, blind spots, failures, growth areas).
- **5**: Genuine weakness acknowledged, concrete evidence, active remediation
- **4**: Honest reflection with some evidence
- **3**: Real issue named but hedged/softened
- **2**: Weakness is quickly neutralized or reframed as strength
- **1**: Rehearsed non-answer / evasive response

For non-introspective prompts, omit `self_awareness`.

## Flags

Raise flags when applicable:
- `GENERIC RESPONSE` — no role/company specificity
- `REHEARSED NON-ANSWER` — canned weakness answer with evasion
- `VAGUE SKILL ANSWER` — skill mention without concrete usage evidence
- `STAR STORY EMBEDDED` — candidate supplies a specific past example inside non-behavioral question
- `CONTENT-FREE RESUME WALK` — resume walk has no concrete roles/achievements
- `EVASIVE FUTURE ANSWER` — no clear direction in future-planning question

## Overall

Set `overall.score` to `0.0` in model output; overall is computed client-side from per-dimension scores.
