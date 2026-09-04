import json
import unittest

from emojiseq import Role, analyze, format_report


class AnalyzeTests(unittest.TestCase):
    def test_single_codepoint(self):
        result = analyze("🍕")
        self.assertEqual(result.kind, "single_codepoint")
        self.assertEqual(len(result.codepoints), 1)
        self.assertEqual(result.codepoints[0].role, Role.BASE)

    def test_flag_sequence_is_two_regional_indicators(self):
        result = analyze("🇨🇦")
        self.assertEqual(result.kind, "flag_sequence")
        self.assertEqual(len(result.codepoints), 2)
        self.assertTrue(all(c.role == Role.REGIONAL_INDICATOR for c in result.codepoints))

    def test_zwj_sequence(self):
        # family: man, woman, girl, boy joined by ZWJ
        family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"
        result = analyze(family)
        self.assertEqual(result.kind, "zwj_sequence")

    def test_skin_tone_modifier(self):
        result = analyze("\U0001F44D\U0001F3FD")
        self.assertEqual(result.kind, "modified_emoji")

    def test_keycap_sequence(self):
        result = analyze("3️⃣")
        self.assertEqual(result.kind, "keycap_sequence")

    def test_empty_string(self):
        result = analyze("")
        self.assertEqual(result.kind, "empty")
        self.assertEqual(result.codepoints, ())


class FormatReportTests(unittest.TestCase):
    def test_json_output_round_trips(self):
        result = analyze("🍕")
        payload = json.loads(format_report(result, as_json=True))
        self.assertEqual(payload["kind"], "single_codepoint")
        self.assertEqual(payload["codepoint_count"], 1)
        self.assertEqual(payload["codepoints"][0]["codepoint"], "U+1F355")

    def test_text_output_has_one_line_per_codepoint_plus_header(self):
        result = analyze("🇨🇦")
        text = format_report(result, as_json=False)
        self.assertEqual(len(text.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
