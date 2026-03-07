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


class GuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current_position = {
            "open": True,
            "stop_loss": 100.0,
            "take_profit": 130.0,
            "side": "long",
        }

    def test_guardrail_clamps_looser_stop(self) -> None:
        decision = {
            "decision": "BUY",
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "confidence_pct": 66.0,
            "rationale": "BUY setup remains valid.",
        }

        adjusted = apply_trailing_stop_guardrail(
            decision, self.current_position, current_price=120.0
        )

        self.assertEqual(adjusted["stop_loss"], 100.0)
        self.assertIn("SYSTEM WARNING:", adjusted["rationale"])
        self.assertEqual(decision["stop_loss"], 95.0)

    def test_guardrail_allows_tighter_stop(self) -> None:
        decision = {
            "decision": "HOLD",
            "stop_loss": 104.0,
            "take_profit": 130.0,
            "confidence_pct": 61.0,
            "rationale": "Hold while tightening risk.",
        }

        adjusted = apply_trailing_stop_guardrail(
            decision, self.current_position, current_price=120.0
        )

        self.assertEqual(adjusted["stop_loss"], 104.0)
        self.assertNotIn("SYSTEM WARNING:", adjusted["rationale"])

    def test_guardrail_raises_for_missing_stop_on_open_long(self) -> None:
        decision = {
            "decision": "BUY",
            "stop_loss": None,
            "take_profit": 130.0,
            "confidence_pct": 58.0,
            "rationale": "BUY but missing stop.",
        }

        with self.assertRaisesRegex(ValueError, "numeric stop_loss"):
            apply_trailing_stop_guardrail(decision, self.current_position)

    def test_guardrail_skips_validation_for_sell_close(self) -> None:
        decision = {
            "decision": "SELL",
            "stop_loss": None,
            "take_profit": None,
            "confidence_pct": 64.0,
            "rationale": "Close the position.",
        }

        adjusted = apply_trailing_stop_guardrail(decision, self.current_position)
        self.assertIsNone(adjusted["stop_loss"])
        self.assertEqual(adjusted["rationale"], "Close the position.")


if __name__ == "__main__":
    unittest.main()
