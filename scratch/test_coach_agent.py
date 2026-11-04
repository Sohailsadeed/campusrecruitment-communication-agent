"""Integration test for Autonomous Curriculum Coach Agent and API endpoints."""
import os
import sys
import unittest
sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestCurriculumCoach(unittest.TestCase):
    def test_01_active_plan_initial(self):
        resp = client.get("/api/coach/active-plan")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("has_plan", data)

    def test_02_generate_plan(self):
        resp = client.post(
            "/api/coach/generate-plan",
            json={"target_role": "Strategy Consultant", "force_replan": True},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("has_plan"))
        plan = data.get("plan")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.get("days", [])), 7)
        self.assertIn("identified_bottlenecks", plan)

        # Check Day 1
        day1 = plan["days"][0]
        self.assertEqual(day1["day_number"], 1)
        self.assertIn(day1["status"], ["in_progress", "pending"])
        self.assertIn("drill_route", day1)
        self.assertTrue(day1["drill_route"].startswith("/"))

    def test_03_complete_day(self):
        # Fetch active plan
        resp = client.get("/api/coach/active-plan")
        data = resp.json()
        self.assertTrue(data.get("has_plan"))
        plan_id = data["plan"]["id"]

        # Complete Day 1
        complete_resp = client.post(
            "/api/coach/complete-day",
            json={"plan_id": plan_id, "day_number": 1, "score_achieved": 84.5},
        )
        self.assertEqual(complete_resp.status_code, 200)
        res_data = complete_resp.json()
        self.assertTrue(res_data.get("success"))

        # Verify Day 1 is completed and Day 2 is unlocked
        updated_plan = client.get("/api/coach/active-plan").json()["plan"]
        d1 = updated_plan["days"][0]
        d2 = updated_plan["days"][1]
        self.assertEqual(d1["status"], "completed")
        self.assertEqual(d1["score_achieved"], 84.5)
        self.assertIsNotNone(d1["completed_at"])
        self.assertEqual(d2["status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
