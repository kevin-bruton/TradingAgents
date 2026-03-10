import unittest

from backtest import (
    POSITION_STATUS_CLOSED_SELL,
    POSITION_STATUS_CLOSED_STOP_LOSS,
    POSITION_STATUS_CLOSED_TAKE_PROFIT,
    POSITION_STATUS_OPEN,
    advance_position_from_history_row,
    apply_decision_transition,
    apply_price_range_exits,
    simulate_position_day,
)


class BacktestLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.closed_position = {
            "open": False,
            "stop_loss": None,
            "take_profit": None,
            "side": "long",
        }
        self.open_position = {
            "open": True,
            "stop_loss": 100.0,
            "take_profit": 120.0,
            "side": "long",
        }

    def test_apply_decision_transition_buy_opens_position(self) -> None:
        decision = {
            "decision": "BUY",
            "stop_loss": 98.5,
            "take_profit": 130.0,
            "confidence_pct": 71.0,
            "rationale": "Enter on momentum continuation.",
        }

        updated = apply_decision_transition(self.closed_position, decision)

        self.assertTrue(updated["open"])
        self.assertEqual(updated["stop_loss"], 98.5)
        self.assertEqual(updated["take_profit"], 130.0)

    def test_apply_decision_transition_sell_closes_position(self) -> None:
        decision = {
            "decision": "SELL",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 68.0,
            "rationale": "Exit on trend reversal.",
        }

        updated = apply_decision_transition(self.open_position, decision)

        self.assertFalse(updated["open"])
        self.assertIsNone(updated["stop_loss"])
        self.assertIsNone(updated["take_profit"])

    def test_apply_price_range_exits_prioritizes_stop_loss(self) -> None:
        updated, reason = apply_price_range_exits(
            self.open_position,
            day_low=99.0,
            day_high=121.0,
        )

        self.assertFalse(updated["open"])
        self.assertEqual(reason, "STOP_LOSS_HIT")

    def test_simulate_position_day_returns_take_profit_close_status(self) -> None:
        decision = {
            "decision": "BUY",
            "stop_loss": 95.0,
            "take_profit": 105.0,
            "confidence_pct": 76.0,
            "rationale": "Breakout setup is intact.",
        }

        updated, status, note = simulate_position_day(
            self.closed_position,
            decision,
            day_low=100.0,
            day_high=106.0,
        )

        self.assertFalse(updated["open"])
        self.assertEqual(status, POSITION_STATUS_CLOSED_TAKE_PROFIT)
        self.assertIn("Take-profit was triggered", note)

    def test_simulate_position_day_returns_closed_sell_status(self) -> None:
        decision = {
            "decision": "SELL",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 64.0,
            "rationale": "De-risk before potential drawdown.",
        }

        updated, status, note = simulate_position_day(
            self.open_position,
            decision,
            day_low=102.0,
            day_high=108.0,
        )

        self.assertFalse(updated["open"])
        self.assertEqual(status, POSITION_STATUS_CLOSED_SELL)
        self.assertIsNone(note)

    def test_advance_position_from_history_row_parses_legacy_payload(self) -> None:
        history_row = {
            "decision": (
                "{'decision': 'BUY', 'stop_loss': 97.5, "
                "'take_profit': 125.0, 'confidence_pct': 73.0, "
                "'rationale': 'Legacy payload'}"
            ),
            "stop_loss": None,
            "take_profit": None,
            "position_status": None,
        }

        updated = advance_position_from_history_row(self.closed_position, history_row)

        self.assertTrue(updated["open"])
        self.assertEqual(updated["stop_loss"], 97.5)
        self.assertEqual(updated["take_profit"], 125.0)

    def test_advance_position_from_history_row_uses_position_status(self) -> None:
        history_row = {
            "decision": "BUY",
            "stop_loss": 99.0,
            "take_profit": 123.0,
            "position_status": POSITION_STATUS_CLOSED_STOP_LOSS,
        }

        updated = advance_position_from_history_row(self.open_position, history_row)

        self.assertFalse(updated["open"])
        self.assertIsNone(updated["stop_loss"])
        self.assertIsNone(updated["take_profit"])

    def test_simulate_position_day_keeps_open_without_trigger(self) -> None:
        decision = {
            "decision": "HOLD",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 55.0,
            "rationale": "No change today.",
        }

        updated, status, note = simulate_position_day(
            self.open_position,
            decision,
            day_low=101.0,
            day_high=119.0,
        )

        self.assertTrue(updated["open"])
        self.assertEqual(status, POSITION_STATUS_OPEN)
        self.assertIsNone(note)


if __name__ == "__main__":
    unittest.main()
