import unittest

from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.position_management.guardrails import apply_trailing_stop_guardrail


def _build_signal(
    *,
    decision: str = "BUY",
    stop_loss: float | None = 101.5,
    take_profit: float | None = 120.0,
    confidence_pct: float = 72.5,
    rationale: str = "Confluence across analysts supports the plan.",
) -> str:
    return (
        "Portfolio manager summary.\n"
        "```json\n"
        "{\n"
        f'  "decision": "{decision}",\n'
        f'  "stop_loss": {stop_loss if stop_loss is not None else "null"},\n'
        f'  "take_profit": {take_profit if take_profit is not None else "null"},\n'
        f'  "confidence_pct": {confidence_pct},\n'
        f'  "rationale": "{rationale}"\n'
        "}\n"
        "```"
    )


class SignalProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.processor = SignalProcessor()

    def test_process_signal_parses_structured_json_block(self) -> None:
        signal = _build_signal()
        parsed = self.processor.process_signal(signal)
        self.assertEqual(parsed["decision"], "BUY")
        self.assertEqual(parsed["stop_loss"], 101.5)
        self.assertEqual(parsed["take_profit"], 120.0)
        self.assertEqual(parsed["confidence_pct"], 72.5)
        self.assertEqual(
            parsed["rationale"], "Confluence across analysts supports the plan."
        )

    def test_process_signal_rejects_missing_json_block(self) -> None:
        with self.assertRaisesRegex(ValueError, "No fenced ```json``` block"):
            self.processor.process_signal("No structured output")

    def test_process_signal_rejects_multiple_json_blocks(self) -> None:
        signal = f"{_build_signal()}\n{_build_signal(decision='SELL')}"
        with self.assertRaisesRegex(ValueError, "Expected exactly one"):
            self.processor.process_signal(signal)

    def test_process_signal_rejects_out_of_range_confidence(self) -> None:
        signal = _build_signal(confidence_pct=120)
        with self.assertRaisesRegex(ValueError, "confidence_pct"):
            self.processor.process_signal(signal)

    def test_process_signal_rejects_short_entry_in_long_only_mode(self) -> None:
        signal = _build_signal(decision="SELL_SHORT", stop_loss=120.0)
        with self.assertRaisesRegex(ValueError, "not allowed for position_mode 'long_only'"):
            self.processor.process_signal(signal, position_mode="long_only")

    def test_process_signal_accepts_buy_to_cover_for_open_short(self) -> None:
        signal = _build_signal(
            decision="BUY_TO_COVER",
            stop_loss=None,
            take_profit=None,
            confidence_pct=61.0,
        )
        current_position = {
            "open": True,
            "stop_loss": 120.0,
            "take_profit": 95.0,
            "side": "short",
        }
        parsed = self.processor.process_signal(
            signal,
            current_position=current_position,
            position_mode="long_short",
        )
        self.assertEqual(parsed["decision"], "BUY_TO_COVER")


class GuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current_long_position = {
            "open": True,
            "stop_loss": 100.0,
            "take_profit": 130.0,
            "side": "long",
        }
        self.current_short_position = {
            "open": True,
            "stop_loss": 125.0,
            "take_profit": 95.0,
            "side": "short",
        }

    def test_guardrail_clamps_looser_long_stop(self) -> None:
        decision = {
            "decision": "MODIFY",
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "confidence_pct": 66.0,
            "rationale": "Tighten risk setup.",
        }

        adjusted = apply_trailing_stop_guardrail(
            decision, self.current_long_position, current_price=120.0
        )

        self.assertEqual(adjusted["stop_loss"], 100.0)
        self.assertIn("SYSTEM WARNING:", adjusted["rationale"])
        self.assertEqual(decision["stop_loss"], 95.0)

    def test_guardrail_allows_tighter_long_stop(self) -> None:
        decision = {
            "decision": "MODIFY",
            "stop_loss": 104.0,
            "take_profit": 130.0,
            "confidence_pct": 61.0,
            "rationale": "Hold while tightening risk.",
        }

        adjusted = apply_trailing_stop_guardrail(
            decision, self.current_long_position, current_price=120.0
        )

        self.assertEqual(adjusted["stop_loss"], 104.0)
        self.assertNotIn("SYSTEM WARNING:", adjusted["rationale"])

    def test_guardrail_preserves_existing_stop_when_missing(self) -> None:
        decision = {
            "decision": "MODIFY",
            "stop_loss": None,
            "take_profit": 130.0,
            "confidence_pct": 58.0,
            "rationale": "Adjust target only.",
        }

        adjusted = apply_trailing_stop_guardrail(decision, self.current_long_position)
        self.assertEqual(adjusted["stop_loss"], 100.0)
        self.assertIn("SYSTEM WARNING:", adjusted["rationale"])

    def test_guardrail_skips_validation_for_sell_close(self) -> None:
        decision = {
            "decision": "SELL",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 64.0,
            "rationale": "Close the position.",
        }

        adjusted = apply_trailing_stop_guardrail(decision, self.current_long_position)
        self.assertIsNone(adjusted["stop_loss"])
        self.assertEqual(adjusted["rationale"], "Close the position.")

    def test_guardrail_clamps_looser_short_stop(self) -> None:
        decision = {
            "decision": "MODIFY",
            "stop_loss": 130.0,
            "take_profit": 90.0,
            "confidence_pct": 63.0,
            "rationale": "Adjust short risk.",
        }

        adjusted = apply_trailing_stop_guardrail(
            decision, self.current_short_position, current_price=110.0
        )
        self.assertEqual(adjusted["stop_loss"], 125.0)
        self.assertIn("SYSTEM WARNING:", adjusted["rationale"])


if __name__ == "__main__":
    unittest.main()
