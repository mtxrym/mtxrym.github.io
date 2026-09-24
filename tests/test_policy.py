import unittest
from pathlib import Path

import yaml

from src.policy import load_policy, parse_policy

ROOT = Path(__file__).resolve().parents[1]


class PolicyTest(unittest.TestCase):
    def test_repo_policy_loads(self):
        policy = load_policy()
        self.assertAlmostEqual(sum(policy.weights.values()), 1.0, places=3)
        self.assertGreaterEqual(policy.retention_days, policy.window_days)

    def test_workflow_cron_matches_policy(self):
        """抓取频率只能写在 workflow 里，这里保证它和 update_policy.yaml 中的说明一致。"""
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "update-content.yml").read_text(encoding="utf-8"))
        triggers = workflow.get("on") or workflow.get(True)  # PyYAML 会把裸 on 解析成 True
        crons = [entry["cron"] for entry in triggers["schedule"]]
        self.assertEqual(crons, [load_policy().schedule_cron])

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            parse_policy({"scoring": {"weights": {"hype": 1}}})
        with self.assertRaises(ValueError):
            parse_policy({"selection": {"window_days": 10}, "archive": {"retention_days": 5}})
        with self.assertRaises(ValueError):
            parse_policy({"selection": {"max_items": 0}})


if __name__ == "__main__":
    unittest.main()
