# Agent 2 Structure Review Prompt

Iteration: 2

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

Source: input data/test/interview_05_poor.txt
Review iteration: 2

--- Compact transcript and current structure ---
{
  "transcript_turns": [
    {
      "turn_index": 1,
      "speaker": "interviewer",
      "text": "Hi Sam, I\u2019m Kira, nice to meet you. How\u2019s your day going so far?"
    },
    {
      "turn_index": 2,
      "speaker": "candidate",
      "text": "Hey Kira, it\u2019s going okay. Just a little tired from the commute, you know?"
    },
    {
      "turn_index": 3,
      "speaker": "interviewer",
      "text": "Got it. Well, let\u2019s dive in. Can you walk me through your resume and highlight the parts most relevant to this role?"
    },
    {
      "turn_index": 4,
      "speaker": "candidate",
      "text": "Sure. So, I\u2019ve been working as a machine learning engineer for about three years now. I started at a small startup where I did a little bit of everything\u2014data cleaning, model training, that sort of thing. Then I moved to my current job at DataFlow, where I wor..."
    },
    {
      "turn_index": 5,
      "speaker": "interviewer",
      "text": "Interesting. Can you tell me more about the recommendation systems you\u2019ve worked on? What was the scale, and what kind of impact did they have?"
    },
    {
      "turn_index": 6,
      "speaker": "candidate",
      "text": "Yeah, so at DataFlow, we built a recommendation system for our e-commerce platform. It suggests products to users based on their browsing history. The scale was pretty big\u2014I think we had like a million users or something. The impact? Well, it worked okay. Peop..."
    },
    {
      "turn_index": 7,
      "speaker": "interviewer",
      "text": "What kind of metrics did you use to measure success, and how did the system perform against those?"
    },
    {
      "turn_index": 8,
      "speaker": "candidate",
      "text": "We mostly looked at click-through rates. I think it was around 5% or so, which was fine. Not amazing, but not terrible either. We didn\u2019t really track anything else, like revenue or long-term engagement."
    },
    {
      "turn_index": 9,
      "speaker": "interviewer",
      "text": "Got it. Why are you interested in TideStream specifically, and what excites you about the Recommendations team?"
    },
    {
      "turn_index": 10,
      "speaker": "candidate",
      "text": "I\u2019ve heard TideStream is a cool company, and the Recommendations team sounds interesting. I like working on stuff that people actually use, so that\u2019s a plus. Plus, I\u2019ve been at my current job for a while, and I\u2019m ready for a change."
    },
    {
      "turn_index": 11,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about feature stores. Can you explain what a feature store is and how you\u2019ve used one in your work?"
    },
    {
      "turn_index": 12,
      "speaker": "candidate",
      "text": "A feature store is like a place where you store features for your models. I\u2019ve used one before\u2014it was called Feast, I think. We put features in there so we didn\u2019t have to compute them every time we trained a model. It was pretty straightforward."
    },
    {
      "turn_index": 13,
      "speaker": "interviewer",
      "text": "How did you ensure consistency between the features used in training and those served in production?"
    },
    {
      "turn_index": 14,
      "speaker": "candidate",
      "text": "Oh, we just made sure to use the same feature store for both. I think the team had some scripts to check that the features matched, but I wasn\u2019t really involved in that part."
    },
    {
      "turn_index": 15,
      "speaker": "interviewer",
      "text": "Tell me about a time you had to debug a model that was underperforming in production. What was the issue, and how did you resolve it?"
    },
    {
      "turn_index": 16,
      "speaker": "candidate",
      "text": "Once, our model\u2019s performance dropped suddenly. I checked the logs, and it turned out the data pipeline was broken. Some of the features weren\u2019t being updated. I fixed it by restarting the pipeline, and things went back to normal."
    },
    {
      "turn_index": 17,
      "speaker": "interviewer",
      "text": "What steps did you take to diagnose the root cause, and how did you prevent it from happening again?"
    },
    {
      "turn_index": 18,
      "speaker": "candidate",
      "text": "I looked at the logs, and it was pretty obvious the pipeline was broken. To prevent it from happening again, I think we added some alerts, but I\u2019m not sure if that ever got set up."
    },
    {
      "turn_index": 19,
      "speaker": "interviewer",
      "text": "Let\u2019s switch gears. Can you describe a time you had a conflict with a teammate and how you handled it?"
    },
    {
      "turn_index": 20,
      "speaker": "candidate",
      "text": "Yeah, so there was this one guy on my team who always wanted to do things his way. He didn\u2019t like the model I was working on and kept pushing for his own ideas. It was annoying, but I just kind of ignored him and did my own thing."
    },
    {
      "turn_index": 21,
      "speaker": "interviewer",
      "text": "How did that impact the project, and what was the outcome?"
    },
    {
      "turn_index": 22,
      "speaker": "candidate",
      "text": "It didn\u2019t really impact the project much. The model I built worked fine, and his ideas weren\u2019t that great anyway. We just moved on."
    },
    {
      "turn_index": 23,
      "speaker": "interviewer",
      "text": "Tell me about a time you failed at something at work. What happened, and what did you learn?"
    },
    {
      "turn_index": 24,
      "speaker": "candidate",
      "text": "I once deployed a model that turned out to be really bad. The recommendations it gave were way off, and users complained. I had to roll it back pretty quickly."
    },
    {
      "turn_index": 25,
      "speaker": "interviewer",
      "text": "What went wrong, and how did you address it?"
    },
    {
      "turn_index": 26,
      "speaker": "candidate",
      "text": "I think I didn\u2019t test it enough before deploying. After that, I started testing more, but honestly, I didn\u2019t really change much else. It was just one of those things."
    },
    {
      "turn_index": 27,
      "speaker": "interviewer",
      "text": "How do you prioritize your work when you have multiple competing deadlines?"
    },
    {
      "turn_index": 28,
      "speaker": "candidate",
      "text": "I usually just do whatever is due first. If something is really urgent, I\u2019ll work on that, but otherwise, I just go in order."
    },
    {
      "turn_index": 29,
      "speaker": "interviewer",
      "text": "Have you ever had to persuade someone to adopt your approach or idea? How did you go about it?"
    },
    {
      "turn_index": 30,
      "speaker": "candidate",
      "text": "Not really. I mean, I\u2019ve suggested things, but if people don\u2019t want to listen, I don\u2019t push it. It\u2019s not worth the hassle."
    },
    {
      "turn_index": 31,
      "speaker": "interviewer",
      "text": "Can you give an example of a process improvement you\u2019ve made in your work?"
    },
    {
      "turn_index": 32,
      "speaker": "candidate",
      "text": "I automated some of the data cleaning steps at my last job. It saved a little time, but nothing major."
    },
    {
      "turn_index": 33,
      "speaker": "interviewer",
      "text": "What was the impact of that improvement, and how did you measure it?"
    },
    {
      "turn_index": 34,
      "speaker": "candidate",
      "text": "It saved maybe an hour or two a week. I didn\u2019t really measure it, but it felt faster."
    },
    {
      "turn_index": 35,
      "speaker": "interviewer",
      "text": "What\u2019s a weakness you\u2019ve identified in your work, and how are you working to improve it?"
    },
    {
      "turn_index": 36,
      "speaker": "candidate",
      "text": "I\u2019m not great at writing documentation. I know I should do more of it, but I just don\u2019t like it. I\u2019ve been trying to get better, but it\u2019s still not my favorite thing."
    },
    {
      "turn_index": 37,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about A/B testing. Can you walk me through how you\u2019ve designed and analyzed an A/B test for a recommendation system?"
    },
    {
      "turn_index": 38,
      "speaker": "candidate",
      "text": "We ran an A/B test once to see if a new model performed better. We split users into two groups and compared the click-through rates. The new model did slightly better, so we kept it."
    },
    {
      "turn_index": 39,
      "speaker": "interviewer",
      "text": "How did you ensure the test was statistically valid, and what metrics did you track beyond click-through rate?"
    },
    {
      "turn_index": 40,
      "speaker": "candidate",
      "text": "I think we just made sure the groups were big enough. We didn\u2019t really track anything else\u2014just clicks."
    },
    {
      "turn_index": 41,
      "speaker": "interviewer",
      "text": "Have you ever mentored someone or helped a junior teammate grow?"
    },
    {
      "turn_index": 42,
      "speaker": "candidate",
      "text": "Not really. I mean, I\u2019ve answered questions when people asked, but I\u2019ve never been like a formal mentor or anything."
    },
    {
      "turn_index": 43,
      "speaker": "interviewer",
      "text": "What\u2019s something you\u2019ve learned recently that you\u2019re excited to apply in your work?"
    },
    {
      "turn_index": 44,
      "speaker": "candidate",
      "text": "I read about some new deep learning techniques for recommendations. They sound cool, but I haven\u2019t really tried them yet."
    },
    {
      "turn_index": 45,
      "speaker": "interviewer",
      "text": "Do you have any questions for me about the role or the team?"
    },
    {
      "turn_index": 46,
      "speaker": "candidate",
      "text": "Yeah, what\u2019s the team culture like? And how often do you guys work late?"
    },
    {
      "turn_index": 47,
      "speaker": "interviewer",
      "text": "The team is collaborative, and we try to keep a healthy work-life balance, though there are occasional crunch times. Anything else you\u2019d like to know?"
    },
    {
      "turn_index": 48,
      "speaker": "candidate",
      "text": "No, that\u2019s it. Thanks."
    },
    {
      "turn_index": 49,
      "speaker": "interviewer",
      "text": "Great, thanks for your time, Sam. We\u2019ll be in touch."
    },
    {
      "turn_index": 50,
      "speaker": "candidate",
      "text": "Cool, thanks. Bye."
    }
  ],
  "current_cases": [
    {
      "id": 1,
      "turn_type": "behavioral",
      "question": "Got it. Well, let\u2019s dive in. Can you walk me through your resume and highlight the parts most relevant to this role?",
      "response": "Sure. So, I\u2019ve been working as a machine learning engineer for about three years now. I started at a small startup where I did a little bit of everything\u2014data cleaning, model train...",
      "follow_ups": [
        {
          "question": "Interesting. Can you tell me more about the recommendation systems you\u2019ve worked on? What was the scale, and what kind of impact did they have?",
          "response": "Yeah, so at DataFlow, we built a recommendation system for our e-commerce platform. It suggests products to users based on their browsing history. The scale was pretty big\u2014I think...",
          "probe_type": "deepening"
        },
        {
          "question": "What kind of metrics did you use to measure success, and how did the system perform against those?",
          "response": "We mostly looked at click-through rates. I think it was around 5% or so, which was fine. Not amazing, but not terrible either. We didn\u2019t really track anything else, like revenue or...",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 2,
      "turn_type": "behavioral",
      "question": "Got it. Why are you interested in TideStream specifically, and what excites you about the Recommendations team?",
      "response": "I\u2019ve heard TideStream is a cool company, and the Recommendations team sounds interesting. I like working on stuff that people actually use, so that\u2019s a plus. Plus, I\u2019ve been at my...",
      "follow_ups": []
    },
    {
      "id": 3,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about feature stores. Can you explain what a feature store is and how you\u2019ve used one in your work?",
      "response": "A feature store is like a place where you store features for your models. I\u2019ve used one before\u2014it was called Feast, I think. We put features in there so we didn\u2019t have to compute t...",
      "follow_ups": [
        {
          "question": "How did you ensure consistency between the features used in training and those served in production?",
          "response": "Oh, we just made sure to use the same feature store for both. I think the team had some scripts to check that the features matched, but I wasn\u2019t really involved in that part.",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 4,
      "turn_type": "behavioral",
      "question": "Tell me about a time you had to debug a model that was underperforming in production. What was the issue, and how did you resolve it?",
      "response": "Once, our model\u2019s performance dropped suddenly. I checked the logs, and it turned out the data pipeline was broken. Some of the features weren\u2019t being updated. I fixed it by restar...",
      "follow_ups": [
        {
          "question": "What steps did you take to diagnose the root cause, and how did you prevent it from happening again?",
          "response": "I looked at the logs, and it was pretty obvious the pipeline was broken. To prevent it from happening again, I think we added some alerts, but I\u2019m not sure if that ever got set up.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 5,
      "turn_type": "behavioral",
      "question": "Let\u2019s switch gears. Can you describe a time you had a conflict with a teammate and how you handled it?",
      "response": "Yeah, so there was this one guy on my team who always wanted to do things his way. He didn\u2019t like the model I was working on and kept pushing for his own ideas. It was annoying, bu...",
      "follow_ups": [
        {
          "question": "How did that impact the project, and what was the outcome?",
          "response": "It didn\u2019t really impact the project much. The model I built worked fine, and his ideas weren\u2019t that great anyway. We just moved on.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 6,
      "turn_type": "behavioral",
      "question": "Tell me about a time you failed at something at work. What happened, and what did you learn?",
      "response": "I once deployed a model that turned out to be really bad. The recommendations it gave were way off, and users complained. I had to roll it back pretty quickly.",
      "follow_ups": [
        {
          "question": "What went wrong, and how did you address it?",
          "response": "I think I didn\u2019t test it enough before deploying. After that, I started testing more, but honestly, I didn\u2019t really change much else. It was just one of those things.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 7,
      "turn_type": "behavioral",
      "question": "Have you ever had to persuade someone to adopt your approach or idea? How did you go about it?",
      "response": "Not really. I mean, I\u2019ve suggested things, but if people don\u2019t want to listen, I don\u2019t push it. It\u2019s not worth the hassle.",
      "follow_ups": []
    },
    {
      "id": 8,
      "turn_type": "behavioral",
      "question": "How do you prioritize your work when you have multiple competing deadlines?",
      "response": "I usually just do whatever is due first. If something is really urgent, I\u2019ll work on that, but otherwise, I just go in order.",
      "follow_ups": []
    },
    {
      "id": 9,
      "turn_type": "behavioral",
      "question": "Can you give an example of a process improvement you\u2019ve made in your work?",
      "response": "I automated some of the data cleaning steps at my last job. It saved a little time, but nothing major.",
      "follow_ups": [
        {
          "question": "What was the impact of that improvement, and how did you measure it?",
          "response": "It saved maybe an hour or two a week. I didn\u2019t really measure it, but it felt faster.",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 10,
      "turn_type": "behavioral",
      "question": "What\u2019s a weakness you\u2019ve identified in your work, and how are you working to improve it?",
      "response": "I\u2019m not great at writing documentation. I know I should do more of it, but I just don\u2019t like it. I\u2019ve been trying to get better, but it\u2019s still not my favorite thing.",
      "follow_ups": []
    },
    {
      "id": 11,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about A/B testing. Can you walk me through how you\u2019ve designed and analyzed an A/B test for a recommendation system?",
      "response": "We ran an A/B test once to see if a new model performed better. We split users into two groups and compared the click-through rates. The new model did slightly better, so we kept i...",
      "follow_ups": [
        {
          "question": "How did you ensure the test was statistically valid, and what metrics did you track beyond click-through rate?",
          "response": "I think we just made sure the groups were big enough. We didn\u2019t really track anything else\u2014just clicks.",
          "probe_type": "deepening"
        }
      ]
    }
  ]
}
