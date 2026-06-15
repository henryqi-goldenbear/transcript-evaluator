# Agent 2 Structure Review

Iteration: 2
Satisfied: False
Summary: Some follow-ups need to be reattached to the correct parent cases.

## Issues
[
  {
    "severity": "high",
    "case_id": 4,
    "question": "Let\u2019s talk about Airflow. How have you used it in your work, and what\u2019s one thing you\u2019d improve about your current setup?",
    "problem": "This case should be a follow-up to the pipeline improvement case.",
    "correction": "Move this case as a follow-up to case 2."
  },
  {
    "severity": "high",
    "case_id": 3,
    "question": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?",
    "problem": "This case should be a follow-up to the Airflow usage case.",
    "correction": "Move this case as a follow-up to case 4."
  }
]

## Operations
[
  {
    "op": "move_follow_up",
    "reason": "This question is a follow-up to the pipeline improvement case.",
    "source_case_id": 4,
    "target_case_id": 2,
    "follow_up_question": "Let\u2019s talk about Airflow. How have you used it in your work, and what\u2019s one thing you\u2019d improve about your current setup?",
    "response": "I\u2019ve used Airflow to schedule jobs. It\u2019s fine, I guess. I don\u2019t really have any complaints. Maybe if it was easier to debug, but it\u2019s not a big deal.",
    "probe_type": "deepening"
  },
  {
    "op": "move_follow_up",
    "reason": "This question is a follow-up to the Airflow usage case.",
    "source_case_id": 3,
    "target_case_id": 4,
    "follow_up_question": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?",
    "response": "Yeah, once a DAG failed because of a timeout. I just increased the timeout and it worked. Not much else to it.",
    "probe_type": "deepening"
  }
]

## Response
```json
{
  "satisfied": false,
  "summary": "Some follow-ups need to be reattached to the correct parent cases.",
  "issues": [
    {
      "severity": "high",
      "case_id": 4,
      "question": "Let’s talk about Airflow. How have you used it in your work, and what’s one thing you’d improve about your current setup?",
      "problem": "This case should be a follow-up to the pipeline improvement case.",
      "correction": "Move this case as a follow-up to case 2."
    },
    {
      "severity": "high",
      "case_id": 3,
      "question": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?",
      "problem": "This case should be a follow-up to the Airflow usage case.",
      "correction": "Move this case as a follow-up to case 4."
    }
  ],
  "operations": [
    {
      "op": "move_follow_up",
      "reason": "This question is a follow-up to the pipeline improvement case.",
      "source_case_id": 4,
      "target_case_id": 2,
      "follow_up_question": "Let’s talk about Airflow. How have you used it in your work, and what’s one thing you’d improve about your current setup?",
      "response": "I’ve used Airflow to schedule jobs. It’s fine, I guess. I don’t really have any complaints. Maybe if it was easier to debug, but it’s not a big deal.",
      "probe_type": "deepening"
    },
    {
      "op": "move_follow_up",
      "reason": "This question is a follow-up to the Airflow usage case.",
      "source_case_id": 3,
      "target_case_id": 4,
      "follow_up_question": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?",
      "response": "Yeah, once a DAG failed because of a timeout. I just increased the timeout and it worked. Not much else to it.",
      "probe_type": "deepening"
    }
  ]
}
```

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

Source: input data/test/interview_10_poor.txt
Review iteration: 2

--- Compact transcript and current structure ---
{
  "transcript_turns": [
    {
      "turn_index": 1,
      "speaker": "interviewer",
      "text": "Hi Devon, I\u2019m Renee from the Analytics Platform team. Thanks for joining me today\u2014how\u2019s your week been so far?"
    },
    {
      "turn_index": 2,
      "speaker": "candidate",
      "text": "Hey, it\u2019s fine. Pretty busy, you know."
    },
    {
      "turn_index": 3,
      "speaker": "interviewer",
      "text": "Got it. Well, let\u2019s start with a quick walk through your resume. Can you give me the two-minute version of your background and what led you to apply for this role?"
    },
    {
      "turn_index": 4,
      "speaker": "candidate",
      "text": "Sure. I\u2019ve been a data engineer for about four years. Mostly worked at mid-sized companies doing ETL stuff. I\u2019ve used Spark, Airflow, some dbt\u2014pretty standard tools. I applied here because I saw the job posting and it seemed like a good fit."
    },
    {
      "turn_index": 5,
      "speaker": "interviewer",
      "text": "What specifically about Quanta\u2019s analytics platform or the problems we\u2019re solving caught your interest?"
    },
    {
      "turn_index": 6,
      "speaker": "candidate",
      "text": "I mean, logistics is a big industry, right? And data is important everywhere. I figured it\u2019d be a good place to work with data at scale."
    },
    {
      "turn_index": 7,
      "speaker": "interviewer",
      "text": "Got it. Let\u2019s dig into one of your past projects. Can you tell me about a time you built or improved a data pipeline? Walk me through the situation, your role, and the outcome."
    },
    {
      "turn_index": 8,
      "speaker": "candidate",
      "text": "Yeah, so at my last job, we had this pipeline that moved data from our app into a warehouse. It was kind of slow, so I helped make it faster. I used Spark to process the data in batches, and it worked better after that."
    },
    {
      "turn_index": 9,
      "speaker": "interviewer",
      "text": "What was the scale of the data, and how much faster did it get?"
    },
    {
      "turn_index": 10,
      "speaker": "candidate",
      "text": "I don\u2019t remember the exact numbers. It was a lot of data, though. And it was definitely faster\u2014like, noticeably."
    },
    {
      "turn_index": 11,
      "speaker": "interviewer",
      "text": "What challenges did you face while optimizing it?"
    },
    {
      "turn_index": 12,
      "speaker": "candidate",
      "text": "Oh, you know, the usual stuff. Like, Spark can be tricky sometimes. But I figured it out."
    },
    {
      "turn_index": 13,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about Airflow. How have you used it in your work, and what\u2019s one thing you\u2019d improve about your current setup?"
    },
    {
      "turn_index": 14,
      "speaker": "candidate",
      "text": "I\u2019ve used Airflow to schedule jobs. It\u2019s fine, I guess. I don\u2019t really have any complaints. Maybe if it was easier to debug, but it\u2019s not a big deal."
    },
    {
      "turn_index": 15,
      "speaker": "interviewer",
      "text": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?"
    },
    {
      "turn_index": 16,
      "speaker": "candidate",
      "text": "Yeah, once a DAG failed because of a timeout. I just increased the timeout and it worked. Not much else to it."
    },
    {
      "turn_index": 17,
      "speaker": "interviewer",
      "text": "Got it. Let\u2019s shift to dbt. How have you used it to model data in your warehouse?"
    },
    {
      "turn_index": 18,
      "speaker": "candidate",
      "text": "I\u2019ve used dbt to transform data. Like, I\u2019d write models to clean up the data and make it usable for analytics. It\u2019s pretty straightforward."
    },
    {
      "turn_index": 19,
      "speaker": "interviewer",
      "text": "Can you give me an example of a complex transformation you implemented in dbt? What problem were you solving?"
    },
    {
      "turn_index": 20,
      "speaker": "candidate",
      "text": "I don\u2019t know if it was that complex. I had to join a few tables together. It wasn\u2019t a big deal\u2014just wrote a SQL query and put it in dbt."
    },
    {
      "turn_index": 21,
      "speaker": "interviewer",
      "text": "What testing or validation did you put in place for that model?"
    },
    {
      "turn_index": 22,
      "speaker": "candidate",
      "text": "I didn\u2019t really do much testing. I just ran it and checked if the output looked right."
    },
    {
      "turn_index": 23,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about collaboration. Can you tell me about a time you had to work with a stakeholder\u2014like an analyst or product team\u2014to deliver a data solution?"
    },
    {
      "turn_index": 24,
      "speaker": "candidate",
      "text": "Yeah, I worked with an analyst once. They needed some data for a report, so I gave it to them. They were happy with it."
    },
    {
      "turn_index": 25,
      "speaker": "interviewer",
      "text": "What was the ask, and how did you ensure the data met their needs?"
    },
    {
      "turn_index": 26,
      "speaker": "candidate",
      "text": "They wanted a CSV of customer data. I pulled it from the warehouse and sent it over. They didn\u2019t have any issues, so I guess it was fine."
    },
    {
      "turn_index": 27,
      "speaker": "interviewer",
      "text": "Have you ever had a disagreement with a stakeholder about data quality or requirements? How did you handle it?"
    },
    {
      "turn_index": 28,
      "speaker": "candidate",
      "text": "Not really. Most people just trust me to get it right."
    },
    {
      "turn_index": 29,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about leadership. Can you share an example of a time you mentored or guided a junior engineer?"
    },
    {
      "turn_index": 30,
      "speaker": "candidate",
      "text": "I haven\u2019t really mentored anyone. I mean, I\u2019ve shown people how to do things if they asked, but that\u2019s about it."
    },
    {
      "turn_index": 31,
      "speaker": "interviewer",
      "text": "What about process improvements? Have you ever identified a bottleneck or inefficiency in your team\u2019s workflow and proposed a solution?"
    },
    {
      "turn_index": 32,
      "speaker": "candidate",
      "text": "I don\u2019t think so. We had processes in place, and they worked okay. I didn\u2019t see a need to change anything."
    },
    {
      "turn_index": 33,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about failure. Can you tell me about a time a project you worked on didn\u2019t go as planned? What happened, and what did you learn?"
    },
    {
      "turn_index": 34,
      "speaker": "candidate",
      "text": "Hmm. I guess once a pipeline broke because of a schema change. It was an easy fix\u2014I just updated the schema and reran it. Not a big deal."
    },
    {
      "turn_index": 35,
      "speaker": "interviewer",
      "text": "What steps did you take to prevent similar issues in the future?"
    },
    {
      "turn_index": 36,
      "speaker": "candidate",
      "text": "I don\u2019t know. I just made sure to check the schema next time."
    },
    {
      "turn_index": 37,
      "speaker": "interviewer",
      "text": "Let\u2019s do a quick technical deep dive. How would you design a streaming pipeline to handle real-time logistics data, like shipment tracking?"
    },
    {
      "turn_index": 38,
      "speaker": "candidate",
      "text": "I\u2019d use Kafka for the streaming part and Spark to process it. Then write it to a database. Pretty simple."
    },
    {
      "turn_index": 39,
      "speaker": "interviewer",
      "text": "What considerations would you make for scalability or fault tolerance in that pipeline?"
    },
    {
      "turn_index": 40,
      "speaker": "candidate",
      "text": "I guess you\u2019d want to make sure it doesn\u2019t crash. Maybe have some backups or something."
    },
    {
      "turn_index": 41,
      "speaker": "interviewer",
      "text": "How would you handle late-arriving data in that streaming pipeline?"
    },
    {
      "turn_index": 42,
      "speaker": "candidate",
      "text": "I don\u2019t know. Maybe just ignore it? Or update the record later?"
    },
    {
      "turn_index": 43,
      "speaker": "interviewer",
      "text": "Let\u2019s talk about prioritization. How do you decide what to work on when you have multiple competing deadlines?"
    },
    {
      "turn_index": 44,
      "speaker": "candidate",
      "text": "I just do what my manager tells me to do first. If it\u2019s urgent, I\u2019ll do that. Otherwise, I just work through the list."
    },
    {
      "turn_index": 45,
      "speaker": "interviewer",
      "text": "Have you ever had to push back on a request because it wasn\u2019t feasible or aligned with team priorities?"
    },
    {
      "turn_index": 46,
      "speaker": "candidate",
      "text": "Not really. If someone asks for something, I just do it."
    },
    {
      "turn_index": 47,
      "speaker": "interviewer",
      "text": "What\u2019s one technical skill or area you\u2019re actively trying to improve right now?"
    },
    {
      "turn_index": 48,
      "speaker": "candidate",
      "text": "I guess I could learn more about cloud stuff. Like AWS or something. But I haven\u2019t really had time."
    },
    {
      "turn_index": 49,
      "speaker": "interviewer",
      "text": "What\u2019s a weakness you\u2019ve identified in your work, and how are you addressing it?"
    },
    {
      "turn_index": 50,
      "speaker": "candidate",
      "text": "I don\u2019t know. I\u2019m pretty good at what I do. Maybe I could be faster at debugging, but it\u2019s not a big issue."
    },
    {
      "turn_index": 51,
      "speaker": "interviewer",
      "text": "Alright, that\u2019s most of my questions. Do you have any questions for me about the role or the team?"
    },
    {
      "turn_index": 52,
      "speaker": "candidate",
      "text": "Uh, what\u2019s the team like? Like, how many people are on it?"
    },
    {
      "turn_index": 53,
      "speaker": "interviewer",
      "text": "We\u2019re a team of about 10 engineers, split between platform and analytics. Anything else you\u2019d like to know?"
    },
    {
      "turn_index": 54,
      "speaker": "candidate",
      "text": "No, I think that\u2019s it."
    },
    {
      "turn_index": 55,
      "speaker": "interviewer",
      "text": "Great. Well, thanks for your time today, Devon. We\u2019ll be in touch soon."
    },
    {
      "turn_index": 56,
      "speaker": "candidate",
      "text": "Cool, thanks. Bye."
    }
  ],
  "current_cases": [
    {
      "id": 1,
      "turn_type": "behavioral",
      "question": "Got it. Well, let\u2019s start with a quick walk through your resume. Can you give me the two-minute version of your background and what led you to apply for this role?",
      "response": "Sure. I\u2019ve been a data engineer for about four years. Mostly worked at mid-sized companies doing ETL stuff. I\u2019ve used Spark, Airflow, some dbt\u2014pretty standard tools. I applied here...",
      "follow_ups": [
        {
          "question": "What specifically about Quanta\u2019s analytics platform or the problems we\u2019re solving caught your interest?",
          "response": "I mean, logistics is a big industry, right? And data is important everywhere. I figured it\u2019d be a good place to work with data at scale.",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 2,
      "turn_type": "behavioral",
      "question": "Got it. Let\u2019s dig into one of your past projects. Can you tell me about a time you built or improved a data pipeline? Walk me through the situation, your role, and the outcome.",
      "response": "Yeah, so at my last job, we had this pipeline that moved data from our app into a warehouse. It was kind of slow, so I helped make it faster. I used Spark to process the data in ba...",
      "follow_ups": [
        {
          "question": "What was the scale of the data, and how much faster did it get?",
          "response": "I don\u2019t remember the exact numbers. It was a lot of data, though. And it was definitely faster\u2014like, noticeably.",
          "probe_type": "clarifying"
        },
        {
          "question": "What challenges did you face while optimizing it?",
          "response": "Oh, you know, the usual stuff. Like, Spark can be tricky sometimes. But I figured it out.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 3,
      "turn_type": "behavioral",
      "question": "Can you describe a time you had to debug a failing Airflow DAG? What was the issue, and how did you resolve it?",
      "response": "Yeah, once a DAG failed because of a timeout. I just increased the timeout and it worked. Not much else to it.",
      "follow_ups": []
    },
    {
      "id": 4,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about Airflow. How have you used it in your work, and what\u2019s one thing you\u2019d improve about your current setup?",
      "response": "I\u2019ve used Airflow to schedule jobs. It\u2019s fine, I guess. I don\u2019t really have any complaints. Maybe if it was easier to debug, but it\u2019s not a big deal.",
      "follow_ups": []
    },
    {
      "id": 5,
      "turn_type": "behavioral",
      "question": "Got it. Let\u2019s shift to dbt. How have you used it to model data in your warehouse?",
      "response": "I\u2019ve used dbt to transform data. Like, I\u2019d write models to clean up the data and make it usable for analytics. It\u2019s pretty straightforward.",
      "follow_ups": []
    },
    {
      "id": 6,
      "turn_type": "behavioral",
      "question": "Can you give me an example of a complex transformation you implemented in dbt? What problem were you solving?",
      "response": "I don\u2019t know if it was that complex. I had to join a few tables together. It wasn\u2019t a big deal\u2014just wrote a SQL query and put it in dbt.",
      "follow_ups": [
        {
          "question": "What testing or validation did you put in place for that model?",
          "response": "I didn\u2019t really do much testing. I just ran it and checked if the output looked right.",
          "probe_type": "clarifying"
        }
      ]
    },
    {
      "id": 7,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about collaboration. Can you tell me about a time you had to work with a stakeholder\u2014like an analyst or product team\u2014to deliver a data solution?",
      "response": "Yeah, I worked with an analyst once. They needed some data for a report, so I gave it to them. They were happy with it.",
      "follow_ups": [
        {
          "question": "What was the ask, and how did you ensure the data met their needs?",
          "response": "They wanted a CSV of customer data. I pulled it from the warehouse and sent it over. They didn\u2019t have any issues, so I guess it was fine.",
          "probe_type": "deepening"
        },
        {
          "question": "Have you ever had a disagreement with a stakeholder about data quality or requirements? How did you handle it?",
          "response": "Not really. Most people just trust me to get it right.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 8,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about leadership. Can you share an example of a time you mentored or guided a junior engineer?",
      "response": "I haven\u2019t really mentored anyone. I mean, I\u2019ve shown people how to do things if they asked, but that\u2019s about it.",
      "follow_ups": []
    },
    {
      "id": 9,
      "turn_type": "behavioral",
      "question": "What about process improvements? Have you ever identified a bottleneck or inefficiency in your team\u2019s workflow and proposed a solution?",
      "response": "I don\u2019t think so. We had processes in place, and they worked okay. I didn\u2019t see a need to change anything.",
      "follow_ups": []
    },
    {
      "id": 10,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about failure. Can you tell me about a time a project you worked on didn\u2019t go as planned? What happened, and what did you learn?",
      "response": "Hmm. I guess once a pipeline broke because of a schema change. It was an easy fix\u2014I just updated the schema and reran it. Not a big deal.",
      "follow_ups": [
        {
          "question": "What steps did you take to prevent similar issues in the future?",
          "response": "I don\u2019t know. I just made sure to check the schema next time.",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 11,
      "turn_type": "behavioral",
      "question": "Let\u2019s do a quick technical deep dive. How would you design a streaming pipeline to handle real-time logistics data, like shipment tracking?",
      "response": "I\u2019d use Kafka for the streaming part and Spark to process it. Then write it to a database. Pretty simple.",
      "follow_ups": [
        {
          "question": "What considerations would you make for scalability or fault tolerance in that pipeline?",
          "response": "I guess you\u2019d want to make sure it doesn\u2019t crash. Maybe have some backups or something.",
          "probe_type": "deepening"
        },
        {
          "question": "How would you handle late-arriving data in that streaming pipeline?",
          "response": "I don\u2019t know. Maybe just ignore it? Or update the record later?",
          "probe_type": "deepening"
        }
      ]
    },
    {
      "id": 12,
      "turn_type": "behavioral",
      "question": "Have you ever had to push back on a request because it wasn\u2019t feasible or aligned with team priorities?",
      "response": "Not really. If someone asks for something, I just do it.",
      "follow_ups": []
    },
    {
      "id": 13,
      "turn_type": "behavioral",
      "question": "Let\u2019s talk about prioritization. How do you decide what to work on when you have multiple competing deadlines?",
      "response": "I just do what my manager tells me to do first. If it\u2019s urgent, I\u2019ll do that. Otherwise, I just work through the list.",
      "follow_ups": []
    }
  ]
}
