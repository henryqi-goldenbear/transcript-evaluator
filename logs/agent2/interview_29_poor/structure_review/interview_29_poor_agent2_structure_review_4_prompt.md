# Agent 2 Structure Review Prompt

Iteration: 4

## Prompt
You are Agent 2 acting as the structure reviewer for Agent 0.

Agent 0 is txt_to_json.py. It converts a raw interview transcript into evaluator-ready JSON.
Before Agent 1 scores anything, review Agent 0's structure and either approve it or return the
compact correction operations Agent 0 should apply.

Review rules:
- This is not the final QA report. Do not write a narrative audit.
- Your entire response must be one JSON object that can be parsed by json.loads.
- Compare the compact transcript outline against the evaluator JSON outline.
- Main interview questions should be separate cases.
- Dependent probes should be follow_ups on the correct parent case.
- Independent questions should not be attached as follow_ups.
- Greetings, logistics, interviewer explanations, transitions, closings, and candidate questions
  should be non-scorable and omitted.
- Each follow_up must include the candidate response that answers that follow-up.
- probe_type must be "clarifying" when the interviewer asks for missing facts, context, role,
  metrics, timeline, or specificity.
- probe_type must be "deepening" when the interviewer probes reasoning, tradeoffs, consequences,
  reflection, or what happened next.
- Before returning operations, re-inspect current_cases. Do not propose an operation if the
  structure already matches that operation, such as a follow-up already attached to the requested
  parent or the question already promoted to a standalone case.
- If a question should become its own case, use split_follow_up_to_case or add_missing_case, not
  move_follow_up.
- If you cannot express the needed change with the provided operations schema, set
  "satisfied": true, leave operations empty, and describe the limitation in summary instead of
  looping forever.

Return valid JSON only. No markdown, no prose outside JSON.
Your first character must be "{" and your last character must be "}".

Use exactly this schema:
{
  "satisfied": true | false,
  "summary": "one short sentence",
  "issues": [
    {
      "severity": "high" | "medium" | "low",
      "case_id": <number or null>,
      "question": "question or nearby transcript text",
      "problem": "what is structurally wrong",
      "correction": "what Agent 0 should change"
    }
  ],
  "operations": [
    {
      "op": "split_follow_up_to_case" | "add_missing_case" | "remove_case" | "move_follow_up" | "change_probe_type",
      "reason": "why this operation is needed",
      "source_case_id": <number or null>,
      "target_case_id": <number or null>,
      "follow_up_question": "follow-up question text or empty string",
      "question": "main question text or empty string",
      "response": "candidate response text or empty string",
      "turn_type": "behavioral" | "non_behavioral" | "",
      "probe_type": "clarifying" | "deepening" | ""
    }
  ]
}

If satisfied is true, operations must be [].
If satisfied is false, operations must contain compact edits only. Do not return the full corrected JSON.
Prefer split_follow_up_to_case when Agent 0 attached an independent question as a follow-up.
Prefer add_missing_case when a transcript question is absent from the evaluator JSON.

Source: input data/test/interview_29_poor.txt
Review iteration: 4

--- Compact transcript and current structure ---
{
  "transcript_turns": [
    {
      "turn_index": 1,
      "speaker": "interviewer",
      "text": "Hi Avery, thanks for joining today. How\u2019s your morning going so far?"
    },
    {
      "turn_index": 2,
      "speaker": "candidate",
      "text": "Hey Marcus, it\u2019s going okay. Just had some coffee, so I\u2019m good."
    },
    {
      "turn_index": 3,
      "speaker": "interviewer",
      "text": "Great to hear. Why don\u2019t we start with you walking me through your resume? Highlight the parts most relevant to this role on the Growth team."
    },
    {
      "turn_index": 4,
      "speaker": "candidate",
      "text": "Sure. So, I\u2019ve been a frontend developer for about four years now. I worked at TechCorp for two years, then moved to StartupX for another two. Mostly React and JavaScript, some TypeScript. I\u2019ve built a few dashboards and some UI components. Nothing too crazy."
    },
    {
      "turn_index": 5,
      "speaker": "interviewer",
      "text": "Got it. What drew you to Brightlane\u2019s Growth team specifically?"
    },
    {
      "turn_index": 6,
      "speaker": "candidate",
      "text": "Well, I saw the job posting and it seemed like a good fit. I\u2019ve worked on growth stuff before, like sign-up flows and things. I think it\u2019s cool to work on features that help the company grow, you know? Plus, the team seems nice."
    },
    {
      "turn_index": 7,
      "speaker": "interviewer",
      "text": "Can you tell me about a time you optimized the performance of a frontend application? What was the problem, and how did you measure the impact?"
    },
    {
      "turn_index": 8,
      "speaker": "candidate",
      "text": "Oh, yeah, I did that once. There was this page that was loading really slow. I think it was because of some big images or something. So I compressed them and made the page load faster. I didn\u2019t really measure it, but people said it felt quicker."
    },
    {
      "turn_index": 9,
      "speaker": "interviewer",
      "text": "Got it. Let\u2019s shift to teamwork. Tell me about a time you had a disagreement with a teammate. How did you handle it?"
    },
    {
      "turn_index": 10,
      "speaker": "candidate",
      "text": "Hmm, I don\u2019t really like conflict, so I usually just go with what the other person wants. There was this one time when a designer wanted to change the layout of a page, and I thought it was fine the way it was. But I just did what they asked because it\u2019s easie..."
    },
    {
      "turn_index": 11,
      "speaker": "interviewer",
      "text": "I see. How do you prioritize your work when you have multiple competing deadlines?"
    },
    {
      "turn_index": 12,
      "speaker": "candidate",
      "text": "I just kind of do what\u2019s due first. If my manager tells me something is urgent, I\u2019ll work on that. Otherwise, I just pick whatever seems easiest at the time. It\u2019s worked out so far."
    },
    {
      "turn_index": 13,
      "speaker": "interviewer",
      "text": "Tell me about a time you mentored a junior engineer or helped someone on your team grow."
    },
    {
      "turn_index": 14,
      "speaker": "candidate",
      "text": "I don\u2019t know if I\u2019ve really mentored anyone. I\u2019ve shown people how to do small things, like fix a bug or something. But nothing big. I\u2019m not really the teaching type."
    },
    {
      "turn_index": 15,
      "speaker": "interviewer",
      "text": "Fair enough. Let\u2019s talk about A/B testing. Can you walk me through how you\u2019ve designed or implemented an A/B test in the past?"
    },
    {
      "turn_index": 16,
      "speaker": "candidate",
      "text": "Yeah, so we had this button that wasn\u2019t getting clicked enough. So I made two versions of it\u2014one red and one blue\u2014and we just kind of guessed which one worked better. I think the red one did, so we kept that."
    },
    {
      "turn_index": 17,
      "speaker": "interviewer",
      "text": "How did you ensure the test was statistically valid?"
    },
    {
      "turn_index": 18,
      "speaker": "candidate",
      "text": "I\u2019m not really sure. We just ran it for a few days and picked the one that seemed better. I think that\u2019s how it works."
    },
    {
      "turn_index": 19,
      "speaker": "interviewer",
      "text": "Got it. Tell me about a time you failed at something at work. What happened, and what did you learn?"
    },
    {
      "turn_index": 20,
      "speaker": "candidate",
      "text": "Oh, I don\u2019t know. I guess I\u2019ve made small mistakes, like typos in code or something. But nothing big. I just fix them and move on."
    },
    {
      "turn_index": 21,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about TypeScript. How do you use it to improve code quality in a React application?"
    },
    {
      "turn_index": 22,
      "speaker": "candidate",
      "text": "TypeScript is good because it catches errors before you run the code. I use it for props and stuff, so you don\u2019t pass the wrong type. It\u2019s pretty straightforward."
    },
    {
      "turn_index": 23,
      "speaker": "interviewer",
      "text": "Can you give me an example of a time you used TypeScript to prevent a bug?"
    },
    {
      "turn_index": 24,
      "speaker": "candidate",
      "text": "I don\u2019t remember exactly. I think there was a time when it caught a typo in a prop name. So that was helpful, I guess."
    },
    {
      "turn_index": 25,
      "speaker": "interviewer",
      "text": "Tell me about a time you improved a process on your team. What was the problem, and what did you do?"
    },
    {
      "turn_index": 26,
      "speaker": "candidate",
      "text": "I don\u2019t think I\u2019ve really done that. We had standups and stuff, and that worked fine. I didn\u2019t see a need to change anything."
    },
    {
      "turn_index": 27,
      "speaker": "interviewer",
      "text": "How do you stay up to date with frontend technologies and best practices?"
    },
    {
      "turn_index": 28,
      "speaker": "candidate",
      "text": "I read some blogs sometimes and watch YouTube videos. But I don\u2019t go too deep. If something new comes up, I\u2019ll learn it if I need to."
    },
    {
      "turn_index": 29,
      "speaker": "interviewer",
      "text": "Tell me about a time you had to persuade someone to adopt your technical approach. How did you make your case?"
    },
    {
      "turn_index": 30,
      "speaker": "candidate",
      "text": "I don\u2019t usually push for my ideas. If someone else has a better way, I just go with that. It\u2019s easier than arguing."
    },
    {
      "turn_index": 31,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about React. How do you manage state in a large application?"
    },
    {
      "turn_index": 32,
      "speaker": "candidate",
      "text": "I use useState and useEffect a lot. For bigger stuff, I\u2019ve used Redux, but I don\u2019t really like it. It\u2019s kind of complicated."
    },
    {
      "turn_index": 33,
      "speaker": "interviewer",
      "text": "Can you walk me through how you\u2019d debug a performance issue in a React app?"
    },
    {
      "turn_index": 34,
      "speaker": "candidate",
      "text": "I\u2019d probably look at the network tab and see if anything is loading slow. If it\u2019s a React issue, I\u2019d check if there are too many re-renders. But I don\u2019t know all the tools for that."
    },
    {
      "turn_index": 35,
      "speaker": "interviewer",
      "text": "What\u2019s a weakness you\u2019ve identified in your work, and how have you worked to improve it?"
    },
    {
      "turn_index": 36,
      "speaker": "candidate",
      "text": "I guess I\u2019m not great at estimating how long things will take. Sometimes I think something will be quick, but it ends up taking longer. I\u2019m trying to get better at it, but it\u2019s hard."
    },
    {
      "turn_index": 37,
      "speaker": "interviewer",
      "text": "Last question: Do you have any questions for me about the role or the team?"
    },
    {
      "turn_index": 38,
      "speaker": "candidate",
      "text": "Uh, not really. I think I know what the job is about. Maybe how big is the team?"
    },
    {
      "turn_index": 39,
      "speaker": "interviewer",
      "text": "The Growth team is about 10 engineers right now. Anything else you\u2019d like to know?"
    },
    {
      "turn_index": 40,
      "speaker": "candidate",
      "text": "No, that\u2019s it. Thanks."
    },
    {
      "turn_index": 41,
      "speaker": "interviewer",
      "text": "Great, thanks for your time, Avery. We\u2019ll be in touch."
    },
    {
      "turn_index": 42,
      "speaker": "candidate",
      "text": "Cool, thanks. Bye."
    }
  ],
  "current_cases": [
    {
      "id": 1,
      "turn_type": "behavioral",
      "question": "Got it. What drew you to Brightlane\u2019s Growth team specifically?",
      "response": "Well, I saw the job posting and it seemed like a good fit. I\u2019ve worked on growth stuff before, like sign-up flows and things. I think it\u2019s cool to work on features that help the co...",
      "follow_ups": []
    },
    {
      "id": 2,
      "turn_type": "behavioral",
      "question": "Can you tell me about a time you optimized the performance of a frontend application? What was the problem, and how did you measure the impact?",
      "response": "Oh, yeah, I did that once. There was this page that was loading really slow. I think it was because of some big images or something. So I compressed them and made the page load fas...",
      "follow_ups": []
    },
    {
      "id": 3,
      "turn_type": "behavioral",
      "question": "Got it. Let\u2019s shift to teamwork. Tell me about a time you had a disagreement with a teammate. How did you handle it?",
      "response": "Hmm, I don\u2019t really like conflict, so I usually just go with what the other person wants. There was this one time when a designer wanted to change the layout of a page, and I thoug...",
      "follow_ups": []
    },
    {
      "id": 4,
      "turn_type": "behavioral",
      "question": "I see. How do you prioritize your work when you have multiple competing deadlines?",
      "response": "I just kind of do what\u2019s due first. If my manager tells me something is urgent, I\u2019ll work on that. Otherwise, I just pick whatever seems easiest at the time. It\u2019s worked out so far...",
      "follow_ups": []
    },
    {
      "id": 5,
      "turn_type": "behavioral",
      "question": "Tell me about a time you mentored a junior engineer or helped someone on your team grow.",
      "response": "I don\u2019t know if I\u2019ve really mentored anyone. I\u2019ve shown people how to do small things, like fix a bug or something. But nothing big. I\u2019m not really the teaching type.",
      "follow_ups": []
    },
    {
      "id": 6,
      "turn_type": "behavioral",
      "question": "Fair enough. Let\u2019s talk about A/B testing. Can you walk me through how you\u2019ve designed or implemented an A/B test in the past?",
      "response": "Yeah, so we had this button that wasn\u2019t getting clicked enough. So I made two versions of it\u2014one red and one blue\u2014and we just kind of guessed which one worked better. I think the r...",
      "follow_ups": [
        {
          "question": "How did you ensure the test was statistically valid?",
          "response": "I\u2019m not really sure. We just ran it for a few days and picked the one that seemed better. I think that\u2019s how it works.",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 7,
      "turn_type": "behavioral",
      "question": "Got it. Tell me about a time you failed at something at work. What happened, and what did you learn?",
      "response": "Oh, I don\u2019t know. I guess I\u2019ve made small mistakes, like typos in code or something. But nothing big. I just fix them and move on.",
      "follow_ups": []
    },
    {
      "id": 8,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about TypeScript. How do you use it to improve code quality in a React application?",
      "response": "TypeScript is good because it catches errors before you run the code. I use it for props and stuff, so you don\u2019t pass the wrong type. It\u2019s pretty straightforward.",
      "follow_ups": []
    },
    {
      "id": 9,
      "turn_type": "behavioral",
      "question": "Can you give me an example of a time you used TypeScript to prevent a bug?",
      "response": "I don\u2019t remember exactly. I think there was a time when it caught a typo in a prop name. So that was helpful, I guess.",
      "follow_ups": []
    },
    {
      "id": 10,
      "turn_type": "behavioral",
      "question": "Tell me about a time you improved a process on your team. What was the problem, and what did you do?",
      "response": "I don\u2019t think I\u2019ve really done that. We had standups and stuff, and that worked fine. I didn\u2019t see a need to change anything.",
      "follow_ups": []
    },
    {
      "id": 11,
      "turn_type": "behavioral",
      "question": "Tell me about a time you had to persuade someone to adopt your technical approach. How did you make your case?",
      "response": "I don\u2019t usually push for my ideas. If someone else has a better way, I just go with that. It\u2019s easier than arguing.",
      "follow_ups": []
    },
    {
      "id": 12,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about React. How do you manage state in a large application?",
      "response": "I use useState and useEffect a lot. For bigger stuff, I\u2019ve used Redux, but I don\u2019t really like it. It\u2019s kind of complicated.",
      "follow_ups": []
    },
    {
      "id": 13,
      "turn_type": "behavioral",
      "question": "Can you walk me through how you\u2019d debug a performance issue in a React app?",
      "response": "I\u2019d probably look at the network tab and see if anything is loading slow. If it\u2019s a React issue, I\u2019d check if there are too many re-renders. But I don\u2019t know all the tools for that...",
      "follow_ups": []
    },
    {
      "id": 14,
      "turn_type": "behavioral",
      "question": "Great to hear. Why don\u2019t we start with you walking me through your resume? Highlight the parts most relevant to this role on the Growth team.",
      "response": "Sure. So, I\u2019ve been a frontend developer for about four years now. I worked at TechCorp for two years, then moved to StartupX for another two. Mostly React and JavaScript, some Typ...",
      "follow_ups": []
    }
  ]
}
