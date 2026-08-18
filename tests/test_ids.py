import unittest
from datetime import datetime

from anode import ids


class TestIds(unittest.TestCase):
    def test_decision_id_format(self):
        ts = datetime(2026, 8, 19, 10, 32, 1)
        self.assertEqual(ids.decision_id(ts, 42), "DEC-20260819-103201-00042")

    def test_trade_id_format(self):
        ts = datetime(2026, 8, 19, 10, 32, 1)
        self.assertEqual(ids.trade_id(ts, 7), "TRD-20260819-00007")

    def test_next_strategy_id_empty(self):
        self.assertEqual(ids.next_strategy_id([]), "STRAT-001")

    def test_next_strategy_id_sequence(self):
        existing = ["STRAT-001", "STRAT-002", "STRAT-017"]
        self.assertEqual(ids.next_strategy_id(existing), "STRAT-018")

    def test_next_strategy_id_ignores_garbage(self):
        existing = ["STRAT-003", "not-a-strategy", "EXP-009"]
        self.assertEqual(ids.next_strategy_id(existing), "STRAT-004")

    def test_next_experiment_id(self):
        self.assertEqual(ids.next_experiment_id([]), "EXP-001")
        self.assertEqual(ids.next_experiment_id(["EXP-041", "EXP-002"]), "EXP-042")


if __name__ == "__main__":
    unittest.main()
