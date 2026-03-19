import sys
import unittest

sys.path.insert(0, ".")

from agents.orchestrator import OrchestratorAgent
from store import store


class TestOrchestratorRouting(unittest.TestCase):
    def test_direct_supported_route(self):
        decision, error = OrchestratorAgent._build_route_decision("modeling", "dcf_model")
        self.assertIsNone(error)
        self.assertEqual(decision["target_agent"], "modeling")
        self.assertEqual(decision["target_task"], "dcf_model")
        self.assertEqual(decision["confidence"], 1.0)

    def test_alias_resolution(self):
        decision, error = OrchestratorAgent._build_route_decision("modeling", "dcf")
        self.assertIsNone(error)
        self.assertEqual(decision["target_task"], "dcf_model")

    def test_agent_inferred_from_task(self):
        decision, error = OrchestratorAgent._build_route_decision("", "valuation")
        self.assertIsNone(error)
        self.assertEqual(decision["target_agent"], "modeling")
        self.assertEqual(decision["target_task"], "dcf_model")
        self.assertLess(decision["confidence"], 1.0)

    def test_missing_task_fails(self):
        decision, error = OrchestratorAgent._build_route_decision("modeling", "")
        self.assertEqual(decision, {})
        self.assertIsNotNone(error)

    def test_unsupported_route_fails(self):
        decision, error = OrchestratorAgent._build_route_decision("auditor", "audit")
        self.assertEqual(decision, {})
        self.assertIsNotNone(error)

    def test_run_persists_route_decision(self):
        agent = OrchestratorAgent(
            deal_id="test-deal-id",
            input_payload={"agent_type": "modeling", "task_name": "dcf"},
        )
        run_id = agent.run()
        run_record = store.agent_runs.get(run_id)
        self.assertIsNotNone(run_record)
        self.assertEqual(run_record.status, "completed")
        self.assertIn("route_decision", run_record.input_payload)
        self.assertEqual(run_record.input_payload["route_decision"]["target_task"], "dcf_model")


if __name__ == "__main__":
    unittest.main()
