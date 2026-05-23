"""
Test cases for the behavioral interview transcript evaluator.
Each case includes a question, candidate response, and a structured
expected-score block for each STAR dimension.

Weighted score formula (scores are 1–5 per dimension):
  weighted = (filler * 0.10) + (context * 0.20) + (action * 0.40) + (result * 0.30)
  overall  = weighted * 2          # normalised to 0–10

Credibility-risk flag caps action and result at a max of 2 for that answer.
"""

import json


def _overall(filler: int, context: int, action: int, result: int) -> float:
    weighted = filler * 0.10 + context * 0.20 + action * 0.40 + result * 0.30
    return round(weighted * 2, 1)


TEST_CASES = [

    # ── STRONG RESPONSES ────────────────────────────────────────────────────

    {
        "id": 1,
        "label": "Perfect STAR — full detail, quantified result",
        "question": "Tell me about a time you led a project under a tight deadline.",
        "response": (
            "In Q3 2023 at Acme Corp, I led a 5-person engineering team tasked with migrating "
            "our payment service to a new third-party processor before a contract expiry in six weeks. "
            "The stakes were high: missing the deadline would have triggered a $50k/month penalty. "
            "I started by mapping every integration point, then split the work into two parallel tracks — "
            "back-end API work and front-end UI changes — assigning owners and daily check-in cadence. "
            "I personally owned the tokenization layer because it carried the most risk. "
            "When we hit an undocumented rate-limit issue on day 10, I escalated directly to the vendor's "
            "engineering lead and negotiated a temporary limit increase. "
            "We shipped on day 39 — three days early. Transaction success rates held at 99.7%, "
            "and we avoided the penalty entirely. I learned that early risk identification on the critical "
            "path is more valuable than optimistic planning."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words; delivery is deliberate and concise throughout."},
            "context": {"score": 5, "reasoning": "Company (Acme Corp), timeframe (Q3 2023), scope (5-person team, 6-week window), and stakes ($50k/month penalty) all stated explicitly."},
            "action":  {"score": 5, "reasoning": "Consistent 'I' ownership. Steps are specific (mapping integration points, parallel tracks, owning tokenisation layer). Clear rationale for each choice (highest-risk first, direct vendor escalation)."},
            "result":  {"score": 5, "reasoning": "Concrete, quantified outcome (shipped 3 days early, 99.7% success rate, penalty avoided) tied directly to candidate's actions. Includes reflection and learning."},
            "flags":   [],
            "overall": {"score": _overall(5, 5, 5, 5), "reasoning": "All four dimensions at maximum. Perfect STAR delivery — no filler, fully grounded context, consistent personal ownership, and a quantified result with reflection."},
        },
    },

    {
        "id": 2,
        "label": "Strong STAR — no quantification but clear outcome",
        "question": "Describe a situation where you had to persuade a skeptical stakeholder.",
        "response": (
            "At DataFlow Inc. last year, our product team wanted to deprioritize accessibility work "
            "to hit a feature deadline. The VP of Product was skeptical that accessibility was urgent. "
            "I requested a 30-minute slot, prepared a short deck with three things: "
            "user research showing 12% of our power-users rely on screen readers, "
            "a legal risk summary from our counsel, and a two-sprint implementation estimate. "
            "I walked her through each point calmly and addressed her concern that it would slip the roadmap "
            "by showing how the work could run in parallel. "
            "She approved it that afternoon. The accessibility sprint shipped the following quarter "
            "and we received direct positive feedback from two enterprise accounts."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "Clean delivery, no filler words or rambling."},
            "context": {"score": 4, "reasoning": "Company and rough timeframe are present. Stakes (roadmap slip, enterprise risk) are understandable, but the timeframe is imprecise ('last year') and team scope is not stated."},
            "action":  {"score": 5, "reasoning": "Entirely 'I'-driven. Specific preparation steps (deck with three named components). Clear reasoning for how each concern was addressed."},
            "result":  {"score": 4, "reasoning": "Outcome is clear (approval, sprint shipped, enterprise feedback) and tied to candidate's actions, but lacks hard quantification (e.g., retention impact, revenue)."},
            "flags":   [],
            "overall": {"score": _overall(5, 4, 5, 4), "reasoning": "Strong across all dimensions. Action is a full 5; context and result each lose one point for an imprecise timeframe and absent hard quantification respectively."},
        },
    },

    {
        "id": 3,
        "label": "Good STAR — minor filler, mostly solid",
        "question": "Tell me about a time you had a conflict with a teammate.",
        "response": (
            "So, um, at my previous company — Vertex Labs — around mid-2022, I had a disagreement "
            "with a senior engineer about the testing strategy for a new microservice. "
            "He wanted to skip unit tests and go straight to integration tests for speed. "
            "I felt that was risky given the service handled billing logic. "
            "I brought it up in our next 1-on-1 rather than in the group standup — "
            "I didn't want it to feel like a public challenge. "
            "I laid out specific failure scenarios where unit tests would catch bugs integration tests would miss. "
            "We agreed on a hybrid approach: light unit tests on the business logic layer, "
            "full integration tests everywhere else. The service launched with zero billing errors "
            "in the first month, which validated the approach."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "'So' and 'um' appear at the very start but do not recur or disrupt the rest of the answer."},
            "context": {"score": 4, "reasoning": "Company (Vertex Labs) and timeframe (mid-2022) given. Scope and stakes (billing service) are clear, though team size and project scope are not specified."},
            "action":  {"score": 5, "reasoning": "Consistently 'I'-driven. Deliberate choice to use 1-on-1 over standup is explained. Specific technical argument (failure scenario comparison) shows clear judgment."},
            "result":  {"score": 4, "reasoning": "Concrete outcome (zero billing errors in first month) and directly tied to the candidate's approach. No broader business metric but the result is credible and specific."},
            "flags":   [],
            "overall": {"score": _overall(4, 4, 5, 4), "reasoning": "High across the board. Opening filler costs one point on delivery; context and result are solid but not fully specified. Strong action score (40% weight) carries the total."},
        },
    },

    # ── MISSING CONTEXT ─────────────────────────────────────────────────────

    {
        "id": 4,
        "label": "Missing context — no company, timeframe, or stakes",
        "question": "Tell me about a time you improved a process.",
        "response": (
            "At my last job, we had a slow deployment process. "
            "I looked at it and figured out we could automate the manual steps with a script. "
            "I wrote the script myself, tested it, and rolled it out to the team. "
            "It ended up saving everyone a lot of time."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "No filler words. Delivery is brief but not rambling."},
            "context": {"score": 2, "reasoning": "'At my last job' is the only anchor — no company name, no timeframe, no scope, no explanation of why the slow process mattered or what was at stake."},
            "action":  {"score": 3, "reasoning": "'I'-driven but vague. 'Looked at it' and 'a script' give no specifics on what the script did, what was automated, or why this approach was chosen over alternatives."},
            "result":  {"score": 2, "reasoning": "'A lot of time' is entirely unquantified and unconnected to a business impact. No reflection or learning mentioned."},
            "flags":   [],
            "overall": {"score": _overall(4, 2, 3, 2), "reasoning": "Below average. Weak context and unquantified result drag down the two highest-weighted dimensions. Clean filler compensates minimally at 10% weight."},
        },
    },

    {
        "id": 5,
        "label": "Completely context-free — story floats",
        "question": "Give me an example of handling a high-pressure situation.",
        "response": (
            "I'm pretty good under pressure. One time things were really stressful and there was "
            "a tight deadline. I stayed late and worked hard to get it done. "
            "My manager was happy with the result."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "No filler words, but the brevity masks the absence of content rather than signalling conciseness."},
            "context": {"score": 1, "reasoning": "No company, no role, no timeframe, no description of what 'it' was or why it was high-pressure. The story has no grounding whatsoever."},
            "action":  {"score": 1, "reasoning": "'Stayed late and worked hard' is the entirety of the action — entirely generic with no specifics, no personal judgment, and no reasoning."},
            "result":  {"score": 1, "reasoning": "Result is attributed solely to manager's reaction, not a concrete outcome. No metrics, no business impact, no reflection."},
            "flags":   [],
            "overall": {"score": _overall(4, 1, 1, 1), "reasoning": "Near-floor score. Context, action, and result all score 1 — the three substantive dimensions (90% of rubric weight) are all failing. Clean filler adds 0.2 above the absolute floor."},
        },
    },

    # ── MISSING ACTION (WE-HEAVY) ────────────────────────────────────────────

    {
        "id": 6,
        "label": "We-heavy — individual contribution unclear",
        "question": "Tell me about a time your team delivered something you're proud of.",
        "response": (
            "In 2021 at Brightline Health, we were building a new patient onboarding portal "
            "that had to launch before open enrollment. It was a big project — the whole team "
            "worked on it for three months. We split into sub-teams and everyone did their part. "
            "We had daily standups and the PM kept us on track. In the end, we launched on time "
            "and patient onboarding time dropped by 40%."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "Clean delivery, no filler words."},
            "context": {"score": 4, "reasoning": "Company (Brightline Health), timeframe (2021, 3-month project), and stakes (open enrollment deadline) are all present and clear."},
            "action":  {"score": 1, "reasoning": "Entirely 'we'-driven throughout. Candidate's individual role, decisions, or contributions are completely absent. Sub-team structure and PM leadership are credited instead."},
            "result":  {"score": 3, "reasoning": "Result is quantified (40% drop in onboarding time) but cannot be attributed to the candidate since no personal actions were described."},
            "flags":   [],
            "overall": {"score": _overall(4, 4, 1, 3), "reasoning": "Pulled down almost entirely by the 'we'-heavy action score (1), which carries 40% of the rubric. Strong context and a quantified result cannot compensate for the invisible individual contribution."},
        },
    },

    {
        "id": 7,
        "label": "Partial 'I' — mixed ownership, rationale absent",
        "question": "Describe a time you introduced a new technology to your team.",
        "response": (
            "At CloudNine in 2022, our team was evaluating whether to adopt Kubernetes. "
            "We did some research and I put together a proof of concept. "
            "I shared it with the team and we discussed it together. "
            "After the discussion, the team decided to move forward. "
            "We adopted it over the next quarter and deployments got faster."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words."},
            "context": {"score": 3, "reasoning": "Company and year are present. But the stakes of the decision (why Kubernetes, what problem it solved) and the candidate's role in initiating it are not established."},
            "action":  {"score": 2, "reasoning": "POC is personal ('I put together') but the adoption decision is diffused back to 'the team'. No rationale for why this approach or technology was right. Mix of 'I' and 'we' with 'we' dominating the decision points."},
            "result":  {"score": 2, "reasoning": "'Deployments got faster' is entirely unquantified. No specific metric, no business impact, no reflection on the rollout."},
            "flags":   [],
            "overall": {"score": _overall(5, 3, 2, 2), "reasoning": "Mixed ownership and vague result keep this below average. Clean filler adds only 0.5 to the weighted total; the weak action score (40% weight) is the dominant drag."},
        },
    },

    # ── MISSING RESULT ───────────────────────────────────────────────────────

    {
        "id": 8,
        "label": "Missing result — story trails off",
        "question": "Tell me about a time you had to learn something quickly.",
        "response": (
            "In my first month at Nexus Labs in January 2023, I was assigned to maintain a legacy "
            "Perl codebase even though I had no prior Perl experience. "
            "The system processed invoices for 200+ clients. "
            "I blocked two hours each morning for focused learning, worked through the O'Reilly Perl book, "
            "and asked the one remaining expert on the team targeted questions rather than broad ones. "
            "I annotated the codebase as I read it so I'd retain it. After about three weeks I was able "
            "to handle bug tickets on my own and started..."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words. Delivery is deliberate."},
            "context": {"score": 5, "reasoning": "Company, timeframe, scope (legacy Perl, 200+ clients), and stakes (first month, no prior experience) are all clearly established."},
            "action":  {"score": 5, "reasoning": "Entirely 'I'-driven. Specific, reasoned steps: time-blocked learning, O'Reilly book, targeted expert questions, annotated reading. Each step shows a deliberate method."},
            "result":  {"score": 1, "reasoning": "Answer is cut off mid-sentence. No result or outcome is provided. This is either incomplete delivery or a credibility signal."},
            "flags":   [],
            "overall": {"score": _overall(5, 5, 5, 1), "reasoning": "Unusually high despite a missing result because all three present dimensions are at maximum. The result score of 1 (30% weight) costs 2.4 points off the ceiling."},
        },
    },

    {
        "id": 9,
        "label": "Result present but vague and disconnected from actions",
        "question": "Tell me about a time you improved team morale.",
        "response": (
            "At my previous company around 2021, the team was pretty burnt out after a long sprint. "
            "I organized a team lunch and suggested we do a retrospective. "
            "We had a good conversation and people seemed happier afterward. "
            "Things went better after that."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler. Brief but clean."},
            "context": {"score": 2, "reasoning": "No company name. 'Around 2021' is imprecise. The scope of the burnout and why it mattered are not established."},
            "action":  {"score": 2, "reasoning": "Actions (lunch, retrospective) are named but not elaborated. No reasoning about why these specific interventions were chosen or what the candidate said/did in the retrospective."},
            "result":  {"score": 2, "reasoning": "'Seemed happier' and 'things went better' are anecdotal impressions, not concrete outcomes. No metrics, no follow-up observation, and the connection to candidate's actions is weak."},
            "flags":   [],
            "overall": {"score": _overall(5, 2, 2, 2), "reasoning": "Thin across context, action, and result. The filler score of 5 adds only 0.5 (10% weight) to a total that is otherwise limited by weak scores across 90% of the rubric."},
        },
    },

    # ── FILLER & REPETITION ──────────────────────────────────────────────────

    {
        "id": 10,
        "label": "Filler-heavy — frequent 'um', 'uh', repetition",
        "question": "Tell me about a time you dealt with ambiguity.",
        "response": (
            "Um, so, yeah, uh — so there was this time, um, where I, like, had to basically, "
            "uh, figure out what the requirements were. Um, my manager wasn't really, like, "
            "super clear on what they wanted, you know? So I kind of, um, had to just, uh, "
            "make some assumptions. I made some assumptions and then I, um, went ahead and "
            "built it. And then, uh, yeah, it worked out, I guess. My manager was okay with it. "
            "So, yeah, I think I handled it well."
        ),
        "expected": {
            "filler":  {"score": 1, "reasoning": "Constant filler ('um', 'uh', 'like', 'you know', 'basically', 'kind of') throughout. Direct repetition of 'I made some assumptions'. Delivery is incoherent and the filler obscures any content."},
            "context": {"score": 1, "reasoning": "No company, no role, no timeframe, no description of what was ambiguous or what the stakes were."},
            "action":  {"score": 1, "reasoning": "'Made some assumptions' and 'went ahead and built it' are the only actions — entirely vague with no specifics, no reasoning, and no indication of what 'it' was."},
            "result":  {"score": 1, "reasoning": "'It worked out, I guess' and 'manager was okay with it' are uncertain, anecdotal, and not tied to any concrete outcome."},
            "flags":   [],
            "overall": {"score": _overall(1, 1, 1, 1), "reasoning": "Floor score. Every dimension scores 1 — constant filler obscures all content and no STAR element is meaningfully present."},
        },
    },

    {
        "id": 11,
        "label": "Moderate filler — disrupts flow but content is recoverable",
        "question": "Give an example of a time you received critical feedback.",
        "response": (
            "Sure, so, um — at Meridian Software in mid-2023, I had a code review where my tech lead "
            "told me that my error-handling patterns were inconsistent across the service. "
            "Honestly, um, that was hard to hear at first. But I asked for specific examples, "
            "uh, and she pointed me to three files. I spent a week refactoring the error handling "
            "to use a centralized pattern, wrote a short doc explaining the new standard, "
            "and added a linting rule to catch future violations. After that my code review times "
            "dropped noticeably — reviewers spent less time on style issues."
        ),
        "expected": {
            "filler":  {"score": 3, "reasoning": "'So', 'um', 'uh', and 'honestly' appear several times and slightly interrupt the flow, but the substantive content is still clearly recoverable."},
            "context": {"score": 4, "reasoning": "Company (Meridian Software) and timeframe (mid-2023) are present. The scope (a code review on a service) and stakes (code quality standard) are understandable, though team size and project aren't specified."},
            "action":  {"score": 5, "reasoning": "Entirely 'I'-driven. Steps are specific (asked for examples, refactored, wrote doc, added lint rule). Each step shows deliberate reasoning about preventing recurrence."},
            "result":  {"score": 3, "reasoning": "Result is present ('code review times dropped') and directionally tied to actions, but 'noticeably' is not quantified. No hard metric or business impact given."},
            "flags":   [],
            "overall": {"score": _overall(3, 4, 5, 3), "reasoning": "Solid action (5, 40% weight) and good context (4) are the anchors. Filler and result both score 3, representing the primary gap between this and a strong answer."},
        },
    },

    # ── CREDIBILITY RISK ────────────────────────────────────────────────────

    {
        "id": 12,
        "label": "Credibility risk — deflects on follow-up probe",
        "question": "Tell me about a time you made a high-stakes technical decision.",
        "follow_up": "That's interesting — can you walk me through how you weighed the trade-offs between the two architectures?",
        "response": (
            "Yes, at Helios Systems in 2022 I led the decision to move our data pipeline from "
            "batch processing to a streaming architecture using Kafka. The pipeline handled "
            "10M events/day and latency was causing customer churn. I evaluated three options, "
            "presented to the CTO, and got sign-off."
        ),
        "follow_up_response": (
            "Yeah, um, so the team looked at the trade-offs and we went with what made the most sense "
            "for our scale. Kafka was the obvious choice in the industry. The team handled most of the "
            "evaluation — I was more involved in the communication side."
        ),
        "expected": {
            "filler":  {"score": 3, "reasoning": "Original answer is clean. Follow-up response introduces 'um' and hedging language, signalling discomfort with the probe."},
            "context": {"score": 4, "reasoning": "Company, year, scope (10M events/day pipeline), and business stakes (customer churn) are clearly established in the original answer."},
            "action":  {"score": 2, "reasoning": "CREDIBILITY RISK APPLIED (cap at 2). Original answer implies strong ownership ('I led', 'I evaluated'). But follow-up deflects to 'the team handled most of the evaluation' and calls Kafka 'the obvious choice' — contradicting the depth claimed in the original. Personal ownership collapses under probing."},
            "result":  {"score": 2, "reasoning": "CREDIBILITY RISK APPLIED (cap at 2). No quantified result was provided even in the original answer. The follow-up adds nothing. Outcome is implied but never stated."},
            "flags":   ["CREDIBILITY RISK: Candidate failed to substantiate after positive probe on architecture trade-off analysis — deflected to team and minimised own role."],
            "overall": {"score": _overall(3, 4, 2, 2), "reasoning": "Credibility risk caps action and result at 2, which together account for 70% of the rubric. Strong context and moderate filler cannot offset the collapse under probing."},
        },
    },

    {
        "id": 13,
        "label": "Credibility risk — repeats original answer verbatim on probe",
        "question": "Describe a time you influenced without authority.",
        "follow_up": "How did you specifically structure your argument to get buy-in from the finance team?",
        "response": (
            "At Lumen Co in 2023 I convinced the finance team to approve budget for a new observability "
            "stack even though it wasn't in the original roadmap. I built the business case and "
            "presented it and they approved it."
        ),
        "follow_up_response": (
            "I built a strong business case and presented it to them. I showed them the value "
            "and they could see it made sense. I presented the case and got them to approve it."
        ),
        "expected": {
            "filler":  {"score": 3, "reasoning": "No filler words, but the repetitive structure of the follow-up response is itself a form of content repetition that signals lack of substance."},
            "context": {"score": 3, "reasoning": "Company and year are present. The situation (off-roadmap budget request) is understandable, but scope, stakeholder count, and budget size are absent."},
            "action":  {"score": 2, "reasoning": "CREDIBILITY RISK APPLIED (cap at 2). Original answer is already thin ('built the business case'). Follow-up response is nearly word-for-word repetition with zero new detail — no structure, no framing, no specific argument mentioned. Candidate cannot elaborate on their own stated actions."},
            "result":  {"score": 2, "reasoning": "CREDIBILITY RISK APPLIED (cap at 2). 'They approved it' is the only result in both responses. No downstream impact, no metric, no reflection."},
            "flags":   ["CREDIBILITY RISK: Candidate failed to substantiate after positive probe on argument structure — repeated original answer verbatim with no new detail."],
            "overall": {"score": _overall(3, 3, 2, 2), "reasoning": "Credibility risk cap applied. Both high-weight dimensions (action 40%, result 30%) are at the credibility floor. Context and filler only partially offset the damage."},
        },
    },

    # ── NON-STAR FORMAT ──────────────────────────────────────────────────────

    {
        "id": 14,
        "label": "Non-STAR — general philosophy instead of specific example",
        "question": "Tell me about a time you failed and what you learned.",
        "response": (
            "I think failure is a huge part of growth. I always try to reflect on what went wrong "
            "and use it as a learning opportunity. I believe that you should embrace failure and "
            "use it to get better. I've definitely made mistakes throughout my career and I've "
            "grown from each of them. I think the most important thing is to stay positive and "
            "keep moving forward."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "No filler words. The answer is fluent but entirely abstract."},
            "context": {"score": 1, "reasoning": "No specific situation is described at all. The entire answer is abstract philosophy with no grounding in a real event."},
            "action":  {"score": 1, "reasoning": "No personal actions described — only general values and beliefs. No 'I did X in situation Y' structure whatsoever."},
            "result":  {"score": 1, "reasoning": "No outcome described. 'I've grown' is a claim without any evidence or specifics."},
            "flags":   ["NO SPECIFIC EXAMPLE: Candidate answered with abstract philosophy rather than a past behavioral example."],
            "overall": {"score": _overall(4, 1, 1, 1), "reasoning": "No real example provided — context, action, and result all floor at 1. Clean filler adds 0.2 above the absolute minimum but cannot compensate for the complete absence of STAR content."},
        },
    },

    {
        "id": 15,
        "label": "Non-STAR — hypothetical instead of past experience",
        "question": "Give me an example of a time you managed competing priorities.",
        "response": (
            "If I were in that situation, I would first list out all my tasks and rank them by urgency "
            "and importance. Then I would communicate with my stakeholders to set expectations. "
            "I would focus on the highest-priority items first and delegate where I could. "
            "I think that's the best way to handle competing priorities."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "Clean delivery. No filler. But the hypothetical framing itself is a structural problem, not a filler issue."},
            "context": {"score": 1, "reasoning": "No past situation described. Hypothetical framing ('if I were') means there is no real situation to evaluate."},
            "action":  {"score": 1, "reasoning": "Actions are described in hypothetical future tense ('I would'). No real actions were taken in a real situation. This is a pattern answer, not a behavioral answer."},
            "result":  {"score": 1, "reasoning": "No real outcome. 'I think that's the best way' is an opinion, not a result from a past experience."},
            "flags":   ["HYPOTHETICAL FRAMING: Candidate answered with a hypothetical ('I would') rather than a past behavioral example. Follow-up required to elicit a real story."],
            "overall": {"score": _overall(4, 1, 1, 1), "reasoning": "Same floor profile as an abstract-philosophy answer. Hypothetical framing means no real situation, action, or result exists to score. Fluent delivery is the only positive signal."},
        },
    },

    {
        "id": 16,
        "label": "Non-STAR — stream of consciousness, no structure",
        "question": "Tell me about a challenging project.",
        "response": (
            "Oh man, there have been so many. I guess the one that comes to mind is when we were "
            "building this platform — it was really complex — and there were a lot of moving parts. "
            "Everyone was stressed. The tech was new and nobody really knew how it worked. "
            "We had some late nights. Eventually it kind of came together, though there were issues. "
            "The client was hard to work with too. It was definitely challenging. I learned a lot "
            "from it I guess. Yeah, it was tough but we got through it."
        ),
        "expected": {
            "filler":  {"score": 2, "reasoning": "Multiple hedges and filler phrases: 'I guess', 'kind of', 'Oh man', 'Yeah'. Not constant but frequent enough to noticeably impede clarity."},
            "context": {"score": 1, "reasoning": "No company, no timeframe, no platform name, no role, no scope. 'This platform' is completely unanchored."},
            "action":  {"score": 1, "reasoning": "No 'I'-driven actions at all. Entirely 'we' narrative describing team stress and late nights. No specific decisions, methods, or personal contributions."},
            "result":  {"score": 1, "reasoning": "'Kind of came together' and 'we got through it' are the only outcomes — vague, uncertain, and unconnected to any specific action."},
            "flags":   [],
            "overall": {"score": _overall(2, 1, 1, 1), "reasoning": "All three substantive dimensions floor at 1. Filler drops to 2 rather than 1 but carries only 10% weight, contributing a negligible 0.2 above the absolute floor."},
        },
    },

    # ── MISSING SINGLE ELEMENTS ──────────────────────────────────────────────

    {
        "id": 17,
        "label": "Missing task — jumps from situation to action",
        "question": "Tell me about a time you improved a team's technical practices.",
        "response": (
            "At Orbit Systems in early 2023, our codebase had grown to 200k lines with almost no "
            "documentation and no consistent code style. I introduced an ESLint config, "
            "wrote a contributing guide, and set up a pre-commit hook to enforce it. "
            "Within two months, code review time dropped by 30% according to our PR analytics."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words. Clean and direct."},
            "context": {"score": 3, "reasoning": "Company and timeframe are clear. The problem scope (200k lines, no docs) is concrete. However, the candidate's role and why this was their problem to solve are not established — the 'task' element of STAR is missing."},
            "action":  {"score": 4, "reasoning": "Mostly 'I'-driven with specific named steps (ESLint config, contributing guide, pre-commit hook). But the rationale for choosing these tools over alternatives is absent."},
            "result":  {"score": 5, "reasoning": "Quantified result (30% drop in code review time) tied directly to candidate's actions, sourced to a concrete data point (PR analytics)."},
            "flags":   [],
            "overall": {"score": _overall(5, 3, 4, 5), "reasoning": "Strong result (5) and solid action (4) drive a high score. Context loses points for the missing task element; everything else is clean."},
        },
    },

    {
        "id": 18,
        "label": "Missing situation — jumps straight to action",
        "question": "Describe a time you mentored someone.",
        "response": (
            "I paired with a junior engineer twice a week for a month. "
            "I gave them structured code review feedback with explanations rather than corrections. "
            "I also assigned them a small feature end-to-end so they'd have full ownership. "
            "By the end of the month they were submitting PRs that needed minimal review. "
            "They were promoted six months later."
        ),
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words. Concise and deliberate."},
            "context": {"score": 1, "reasoning": "No company, no timeframe, no description of the junior engineer's skill level, and no explanation of why mentorship was needed or initiated. The story has no grounding."},
            "action":  {"score": 5, "reasoning": "Entirely 'I'-driven. Steps are specific (twice-weekly pairing, explanatory feedback, end-to-end ownership assignment). Each reflects a deliberate pedagogical choice."},
            "result":  {"score": 5, "reasoning": "Clear, tied-to-action outcome (PRs needing minimal review) plus a strong downstream signal (promotion 6 months later)."},
            "flags":   [],
            "overall": {"score": _overall(5, 1, 5, 5), "reasoning": "Excellent action and result; filler is clean. Context floors at 1 due to zero situational grounding, costing 0.8 off a potential 10 (context carries 20% weight)."},
        },
    },

    # ── EXTREME EDGE CASES ───────────────────────────────────────────────────

    {
        "id": 19,
        "label": "One-liner — completely uninformative",
        "question": "Tell me about a time you showed leadership.",
        "response": "I led a project and it went well.",
        "expected": {
            "filler":  {"score": 5, "reasoning": "No filler words — but brevity is not a virtue here; the answer has nothing to say."},
            "context": {"score": 1, "reasoning": "No company, no project description, no timeframe, no stakes. Zero situational grounding."},
            "action":  {"score": 1, "reasoning": "'Led a project' is the entire action description — no specifics, no steps, no reasoning, no individual contribution visible."},
            "result":  {"score": 1, "reasoning": "'It went well' is the entire result — no metric, no outcome, no reflection."},
            "flags":   [],
            "overall": {"score": _overall(5, 1, 1, 1), "reasoning": "One-liner response. All three substantive STAR dimensions floor at 1. The perfect filler score is technically correct (no filler in a single sentence) but adds only 0.2 to an otherwise floor score."},
        },
    },

    {
        "id": 20,
        "label": "Empty / no response",
        "question": "Give me an example of a time you had to adapt to a major change.",
        "response": "",
        "expected": {
            "filler":  {"score": 1, "reasoning": "No response given. Cannot evaluate filler; scored 1 by default."},
            "context": {"score": 1, "reasoning": "No response given. No context present."},
            "action":  {"score": 1, "reasoning": "No response given. No actions present."},
            "result":  {"score": 1, "reasoning": "No response given. No result present."},
            "flags":   ["NO RESPONSE: Candidate provided no answer. May indicate freeze, pass, or interview cut-off."],
            "overall": {"score": _overall(1, 1, 1, 1), "reasoning": "Absolute floor. No response means every dimension defaults to 1. This is the lowest possible score in the rubric."},
        },
    },

    {
        "id": 21,
        "label": "Pivots to a different example mid-answer",
        "question": "Tell me about a time you disagreed with your manager's decision.",
        "response": (
            "There was a time at my last company where my manager wanted to ship without testing. "
            "I wasn't fully comfortable with that but the team went ahead. "
            "Actually, a better example is when I pushed back on a scope decision — "
            "we were adding too many features and I said we should cut scope. "
            "In the end the team agreed and we shipped a leaner product. "
            "That worked out better."
        ),
        "expected": {
            "filler":  {"score": 3, "reasoning": "'Actually' mid-answer signals a pivot and disrupts coherence. The reset is itself a mild rhetorical filler."},
            "context": {"score": 2, "reasoning": "First example has no company or timeframe. Second example is also context-free. Neither story is anchored in a specific situation."},
            "action":  {"score": 2, "reasoning": "First example shows passivity ('I wasn't comfortable but the team went ahead' — no personal action taken). Second example has 'I said we should cut scope' but no elaboration on how, why, or what the conversation looked like."},
            "result":  {"score": 2, "reasoning": "'Shipped a leaner product' and 'worked out better' are vague. No metric, no connection to specific candidate actions. The abandoned first example has no result at all."},
            "flags":   ["PIVOT: Candidate abandoned first example mid-answer. First example also showed passivity (disagreement not acted on), which may be the reason for the pivot."],
            "overall": {"score": _overall(3, 2, 2, 2), "reasoning": "Mid-answer pivot and passive first example pull all dimensions below average. No single dimension rescues the score; the incoherence and passivity permeate every category."},
        },
    },

    {
        "id": 22,
        "label": "Answers a different question entirely",
        "question": "Tell me about a time you had to make a decision with incomplete information.",
        "response": (
            "I'm really passionate about data-driven decision making. In my current role I've "
            "built several dashboards and reporting pipelines that help the team make better "
            "decisions. I think having good data is crucial. I set up our analytics stack "
            "and now everyone uses it."
        ),
        "expected": {
            "filler":  {"score": 4, "reasoning": "No filler words. Delivery is clear, but the content does not address the question asked."},
            "context": {"score": 2, "reasoning": "Some role context is implied ('current role'), but there is no specific situation matching the question. No scenario of incomplete information is described."},
            "action":  {"score": 2, "reasoning": "Actions described (building dashboards, setting up analytics) are real but entirely unrelated to the question about deciding under uncertainty. No decision-making process under ambiguity is shown."},
            "result":  {"score": 1, "reasoning": "'Now everyone uses it' is a weak result claim and completely disconnected from the question asked. No outcome related to the actual question is provided."},
            "flags":   ["OFF-TOPIC: Candidate answered a different question (building data infrastructure) rather than describing a decision made under uncertainty. Follow-up required to redirect."],
            "overall": {"score": _overall(4, 2, 2, 1), "reasoning": "Off-topic answer. Result floors at 1 because no relevant outcome is described. Action and context score 2 for partial but misdirected content. Clean filler adds 0.4 but cannot compensate."},
        },
    },

]


if __name__ == "__main__":
    import sys

    if "--json" in sys.argv:
        print(json.dumps(TEST_CASES, indent=2))
    else:
        for tc in TEST_CASES:
            exp = tc["expected"]
            print(f"[{tc['id']:02d}] {tc['label']}")
            print(f"  Q: {tc['question']}")
            resp_preview = tc["response"][:120].strip()
            if len(tc["response"]) > 120:
                resp_preview += "..."
            print(f"  R: {resp_preview}")
            if tc.get("follow_up"):
                print(f"  FU: {tc['follow_up']}")
            print(f"  Scores:")
            print(f"    filler:  {exp['filler']['score']}/5  — {exp['filler']['reasoning'][:80]}...")
            print(f"    context: {exp['context']['score']}/5  — {exp['context']['reasoning'][:80]}...")
            print(f"    action:  {exp['action']['score']}/5  — {exp['action']['reasoning'][:80]}...")
            print(f"    result:  {exp['result']['score']}/5  — {exp['result']['reasoning'][:80]}...")
            if exp["flags"]:
                for flag in exp["flags"]:
                    print(f"    FLAG: {flag[:100]}...")
            ov = exp["overall"]
            print(f"    overall: {ov['score']}/10  — {ov['reasoning'][:80]}...")
            print()
