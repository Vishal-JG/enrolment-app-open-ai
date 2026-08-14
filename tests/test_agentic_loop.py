import unittest

from agentic_loop import build_implementation_recommendation


class AgenticLoopTests(unittest.TestCase):
    def test_detects_status_mismatch(self):
        observations = [
            "/students/<student_id> (invalid non-integer id) -> HTTP 404 | body: <p>Student not found.</p>"
        ]

        recommendation = build_implementation_recommendation(observations)

        self.assertIn(
            "/students/<student_id> returned 404 but should return 400.",
            recommendation,
        )

    def test_returns_no_issue_when_all_match(self):
        observations = [
            "/students/by-subject (nonexistent XXX999) -> HTTP 200 | body: <p>No students found for subject code XXX999.</p>"
        ]

        recommendation = build_implementation_recommendation(observations)

        self.assertEqual(
            recommendation,
            "No evidence-backed improvement identified.",
        )


if __name__ == "__main__":
    unittest.main()
