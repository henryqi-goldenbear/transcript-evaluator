import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent1 import txt_to_json as parser  # noqa: E402


def parse(raw: str) -> list[dict]:
    return parser.parse_transcript_to_test_cases(raw, classifier_provider="heuristic")


class TranscriptSegmentationTests(unittest.TestCase):
    def test_generalized_main_question_wording_starts_new_cases(self) -> None:
        cases = parse(
            """INTERVIEWER:
What drew you to this team?
CANDIDATE:
The ledger work maps to my experience.
INTERVIEWER:
How do you partner with design and security?
CANDIDATE:
I align early on tradeoffs and review risks.
"""
        )
        self.assertEqual(2, len(cases))
        self.assertIn("What drew you", cases[0]["question"])
        self.assertIn("How do you partner", cases[1]["question"])

    def test_follow_up_chain_attaches_to_same_parent_case(self) -> None:
        cases = parse(
            """INTERVIEWER:
Tell me about a time you led a project.
CANDIDATE:
I led a migration.
INTERVIEWER:
You mentioned replay logic. What would break there?
CANDIDATE:
Retries could double post.
INTERVIEWER:
What happened next?
CANDIDATE:
We added chaos tests.
"""
        )
        self.assertEqual(1, len(cases))
        self.assertEqual(2, len(cases[0]["follow_ups"]))

    def test_consecutive_interviewer_setup_uses_actual_question_before_answer(self) -> None:
        cases = parse(
            """INTERVIEWER:
Welcome. I lead the reliability team and this interview is for a software role.
INTERVIEWER:
What questions do you have so far?
CANDIDATE:
Nothing for now.
INTERVIEWER:
Okay. So Henry, I'd love to hear what brings you to Visa, where you want to go in your career.
CANDIDATE:
I am interested in reliability engineering because I like building dependable systems.
"""
        )
        self.assertEqual(1, len(cases))
        self.assertIn("what brings you to Visa", cases[0]["question"])
        self.assertIn("reliability engineering", cases[0]["response"])
        self.assertFalse(any("Welcome" in case["question"] for case in cases))

    def test_recording_transcript_export_is_normalized_before_segmentation(self) -> None:
        cases = parse(
            """Priya 00:00
Tell me about a time you led a difficult project.
Alex 00:06
I led a billing migration under a tight deadline.
Priya 00:18
Can you be more specific about your role?
Alex 00:22
I owned the rollback plan and stakeholder updates.
"""
        )
        self.assertEqual(1, len(cases))
        self.assertIn("led a difficult project", cases[0]["question"])
        self.assertIn("billing migration", cases[0]["response"])
        self.assertEqual(1, len(cases[0]["follow_ups"]))

    def test_webvtt_recording_export_is_normalized_before_segmentation(self) -> None:
        cases = parse(
            """WEBVTT

1
00:00:01.000 --> 00:00:04.000
Interviewer: What drew you to this team?

2
00:00:05.000 --> 00:00:10.000
Candidate: The product maps closely to my data platform work.

3
00:00:11.000 --> 00:00:14.000
Interviewer: How do you partner with product managers?

4
00:00:15.000 --> 00:00:20.000
Candidate: I align early on tradeoffs and decision owners.
"""
        )
        self.assertEqual(2, len(cases))
        self.assertIn("What drew you", cases[0]["question"])
        self.assertIn("How do you partner", cases[1]["question"])

    def test_audio_recording_input_uses_transcription_stage(self) -> None:
        transcript = """INTERVIEWER: Tell me about a time you led a difficult project.
CANDIDATE: I led a billing migration under a tight deadline.
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "recording.m4a"
            transcript_dir = Path(temp_dir) / "transcripts"
            audio_path.write_bytes(b"fake audio")
            with patch.object(parser, "transcribe_audio_recording", return_value=transcript) as transcribe:
                raw_text, source, transcript_path = parser.read_recording_input(
                    audio_path,
                    "voxtral-mini-latest",
                    transcript_dir,
                )
            transcript_file_text = transcript_path.read_text(encoding="utf-8")

        self.assertEqual("audio-transcription", source)
        self.assertEqual("recording.txt", transcript_path.name)
        self.assertIn("Tell me about", raw_text)
        self.assertIn("INTERVIEWER:", transcript_file_text)
        transcribe.assert_called_once()
        cases = parse(raw_text)
        self.assertEqual(1, len(cases))
        self.assertIn("billing migration", cases[0]["response"])

    def test_audio_recording_input_labels_unlabeled_transcription(self) -> None:
        transcript = "Tell me about a time you led a project. I led a billing migration."
        labeled = {
            "transcript": """INTERVIEWER:
Tell me about a time you led a project.
CANDIDATE:
I led a billing migration.
"""
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "recording.m4a"
            transcript_dir = Path(temp_dir) / "transcripts"
            audio_path.write_bytes(b"fake audio")
            with patch.object(parser, "transcribe_audio_recording", return_value=transcript):
                with patch.object(parser, "mistral_chat_json", return_value=labeled) as labeler:
                    raw_text, source, transcript_path = parser.read_recording_input(
                        audio_path,
                        "voxtral-mini-latest",
                        transcript_dir,
                    )
                    transcript_file_text = transcript_path.read_text(encoding="utf-8")

        self.assertEqual("audio-transcription", source)
        self.assertIn("INTERVIEWER:", transcript_file_text)
        self.assertIn("CANDIDATE:", raw_text)
        labeler.assert_called_once()

    def test_agent2_compact_response_is_expanded_from_full_transcript(self) -> None:
        raw = """INTERVIEWER:
Tell me about a time you improved a process.
CANDIDATE:
I noticed a slow review loop, wrote a checklist, measured the handoff time, trained the team, and reduced turnaround from three days to one day.
"""
        operations = [
            {
                "op": "add_missing_case",
                "reason": "Add missing case.",
                "question": "Tell me about a time you improved a process.",
                "response": "I noticed a slow review loop, wrote a checklist...",
                "turn_type": "behavioral",
            }
        ]
        cases = parser.apply_agent2_structure_operations([], operations, raw)
        hydrated = parser.hydrate_case_responses_from_transcript(cases, raw)

        self.assertEqual(1, len(hydrated))
        self.assertNotIn("...", hydrated[0]["response"])
        self.assertIn("reduced turnaround from three days to one day", hydrated[0]["response"])

    def test_compact_response_expands_when_interviewer_adds_clarifying_turn_before_answer(self) -> None:
        raw = """INTERVIEWER:
Can you tell me about a time you had to learn a new technology?
INTERVIEWER:
How did you approach learning it?
CANDIDATE:
I learned Redis during a hackathon by attending a workshop, reading the docs, drafting a plan, and applying it that same day.
"""
        cases = [
            {
                "id": 1,
                "question": "Can you tell me about a time you had to learn a new technology?",
                "response": "I learned Redis during a hackathon...",
                "follow_ups": [],
            }
        ]
        hydrated = parser.hydrate_case_responses_from_transcript(cases, raw)

        self.assertNotIn("...", hydrated[0]["response"])
        self.assertIn("applying it that same day", hydrated[0]["response"])

    def test_entire_interview_fixture_segments_expected_cases(self) -> None:
        raw = (ROOT / "input data" / "entire_interview.txt").read_text(encoding="utf-8")
        cases = parse(raw)
        questions = [case["question"] for case in cases]
        follow_up_questions = [
            follow["question"]
            for case in cases
            for follow in case.get("follow_ups", [])
        ]

        self.assertGreaterEqual(len(cases), 18)
        self.assertLessEqual(len(cases), 21)
        self.assertTrue(any("improved a process" in q for q in questions))
        self.assertTrue(any("showed leadership" in q for q in questions))
        self.assertTrue(any("product managers" in q for q in questions))
        self.assertTrue(any("Can you be more specific" in q for q in follow_up_questions))
        self.assertFalse(any("RFC for anything" in q for q in questions))
        self.assertFalse(any("Expected rubric mapping" in q for q in questions))


if __name__ == "__main__":
    unittest.main()
