import unittest

from backtest import (
    POSITION_STATUS_CLOSED_BUY_TO_COVER,
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
        self.open_long_position = {
            "open": True,
            "stop_loss": 100.0,
            "take_profit": 120.0,
            "side": "long",
        }
        self.open_short_position = {
            "open": True,
            "stop_loss": 125.0,
            "take_profit": 95.0,
            "side": "short",
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
        self.assertEqual(updated["side"], "long")
        self.assertEqual(updated["stop_loss"], 98.5)
        self.assertEqual(updated["take_profit"], 130.0)

    def test_apply_decision_transition_sell_short_opens_short(self) -> None:
        decision = {
            "decision": "SELL_SHORT",
            "stop_loss": 126.0,
            "take_profit": 92.0,
            "confidence_pct": 67.0,
            "rationale": "Open short on downside momentum.",
        }

        updated = apply_decision_transition(
            self.closed_position,
            decision,
            position_mode="long_short",
        )

        self.assertTrue(updated["open"])
        self.assertEqual(updated["side"], "short")
        self.assertEqual(updated["stop_loss"], 126.0)

    def test_apply_decision_transition_sell_closes_long_position(self) -> None:
        decision = {
            "decision": "SELL",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 68.0,
            "rationale": "Exit on trend reversal.",
        }

        updated = apply_decision_transition(self.open_long_position, decision)

        self.assertFalse(updated["open"])
        self.assertEqual(updated["side"], "long")
        self.assertIsNone(updated["stop_loss"])
        self.assertIsNone(updated["take_profit"])

    def test_apply_decision_transition_buy_to_cover_closes_short_position(self) -> None:
        decision = {
            "decision": "BUY_TO_COVER",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 65.0,
            "rationale": "Close short as risk/reward weakens.",
        }

        updated = apply_decision_transition(
            self.open_short_position,
            decision,
            position_mode="long_short",
        )

        self.assertFalse(updated["open"])
        self.assertEqual(updated["side"], "short")

    def test_apply_price_range_exits_prioritizes_stop_loss(self) -> None:
        updated, reason = apply_price_range_exits(
            self.open_long_position,
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
            self.open_long_position,
            decision,
            day_low=102.0,
            day_high=108.0,
        )

        self.assertFalse(updated["open"])
        self.assertEqual(status, POSITION_STATUS_CLOSED_SELL)
        self.assertIsNone(note)

    def test_simulate_position_day_returns_closed_buy_to_cover_status(self) -> None:
        decision = {
            "decision": "BUY_TO_COVER",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 62.0,
            "rationale": "Close short before squeeze risk.",
        }

        updated, status, note = simulate_position_day(
            self.open_short_position,
            decision,
            day_low=100.0,
            day_high=112.0,
            position_mode="long_short",
        )

        self.assertFalse(updated["open"])
        self.assertEqual(status, POSITION_STATUS_CLOSED_BUY_TO_COVER)
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

        updated = advance_position_from_history_row(self.open_long_position, history_row)

        self.assertFalse(updated["open"])
        self.assertIsNone(updated["stop_loss"])
        self.assertIsNone(updated["take_profit"])

    def test_advance_position_from_history_row_maps_legacy_hold_to_modify(self) -> None:
        history_row = {
            "decision": "HOLD",
            "stop_loss": None,
            "take_profit": 122.0,
            "position_status": None,
        }

        updated = advance_position_from_history_row(self.open_long_position, history_row)
        self.assertTrue(updated["open"])
        self.assertEqual(updated["stop_loss"], 100.0)
        self.assertEqual(updated["take_profit"], 122.0)

    def test_simulate_position_day_keeps_open_without_trigger(self) -> None:
        decision = {
            "decision": "MODIFY",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 55.0,
            "rationale": "No change today.",
        }

        updated, status, note = simulate_position_day(
            self.open_long_position,
            decision,
            day_low=101.0,
            day_high=119.0,
        )

        self.assertTrue(updated["open"])
        self.assertEqual(status, POSITION_STATUS_OPEN)
        self.assertIsNone(note)


if __name__ == "__main__":
    unittest.main()
