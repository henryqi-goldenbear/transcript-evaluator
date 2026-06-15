import sys
import unittest
from pathlib import Path


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
