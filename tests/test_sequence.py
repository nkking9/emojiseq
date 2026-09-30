import json
import unittest

from emojiseq import (
    Role,
    analyze,
    analyze_all,
    describe,
    flag_sequence,
    format_report,
    is_known_emoji_base,
    split_clusters,
    tag_sequence,
)


class AnalyzeTests(unittest.TestCase):
    def test_single_codepoint(self):
        result = analyze("🍕")
        self.assertEqual(result.kind, "single_codepoint")
        self.assertEqual(len(result.codepoints), 1)
        self.assertEqual(result.codepoints[0].role, Role.BASE)
        self.assertTrue(result.codepoints[0].is_known_base)

    def test_plain_letter_is_not_emoji(self):
        result = analyze("a")
        self.assertEqual(result.kind, "not_emoji")
        self.assertEqual(len(result.codepoints), 1)
        self.assertFalse(result.codepoints[0].is_known_base)

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

    def test_variation_sequence(self):
        # warning sign, text-presentation by default, needs VS16 to be an emoji
        result = analyze("⚠️")
        self.assertEqual(result.kind, "variation_sequence")
        self.assertEqual(len(result.codepoints), 2)
        self.assertEqual(result.codepoints[1].role, Role.VARIATION_SELECTOR)

    def test_keycap_with_variation_selector_is_still_keycap(self):
        # keycap sequences carry a VS16 too, but the combiner takes priority
        result = analyze("3️⃣")
        self.assertEqual(result.kind, "keycap_sequence")

    def test_unjoined_letters_are_multi_codepoint(self):
        result = analyze("ab")
        self.assertEqual(result.kind, "multi_codepoint")
        self.assertEqual(len(result.codepoints), 2)

    def test_two_bare_emoji_with_no_joiner_are_multi_codepoint(self):
        # analyze() takes its whole input as one sequence; back-to-back
        # emoji with no ZWJ between them don't match any recognized shape
        # even though each codepoint is individually a known emoji base.
        # This is exactly why split_clusters/analyze_all exist.
        result = analyze("🍕🍔")
        self.assertEqual(result.kind, "multi_codepoint")
        self.assertTrue(all(c.is_known_base for c in result.codepoints))


class DescribeTests(unittest.TestCase):
    def test_family_is_two_or_more_people_joined_directly(self):
        family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"
        self.assertEqual(describe(analyze(family)), "family")

    def test_two_person_family_is_still_a_family(self):
        man_and_boy = "\U0001F468‍\U0001F466"
        self.assertEqual(describe(analyze(man_and_boy)), "family")

    def test_couple_with_heart(self):
        couple = "\U0001F469‍❤️‍\U0001F468"
        self.assertEqual(describe(analyze(couple)), "couple")

    def test_kiss_takes_priority_over_couple(self):
        kiss = "\U0001F468‍❤️‍\U0001F48B‍\U0001F468"
        self.assertEqual(describe(analyze(kiss)), "kiss")

    def test_profession_is_one_person_and_one_object(self):
        scientist = "\U0001F469‍\U0001F52C"
        self.assertEqual(describe(analyze(scientist)), "profession")

    def test_non_zwj_sequence_returns_none(self):
        self.assertIsNone(describe(analyze("🍕")))

    def test_unrecognized_zwj_shape_returns_none(self):
        # rainbow flag: waving white flag + ZWJ + rainbow, no person component
        rainbow_flag = "\U0001F3F3️‍\U0001F308"
        self.assertIsNone(describe(analyze(rainbow_flag)))


class IsKnownEmojiBaseTests(unittest.TestCase):
    def test_recognizes_common_emoji_blocks(self):
        self.assertTrue(is_known_emoji_base(ord("🍕")))
        self.assertTrue(is_known_emoji_base(ord("👍")))
        self.assertTrue(is_known_emoji_base(ord("⚡")))

    def test_recognizes_emoji_outside_the_main_blocks(self):
        # Blood-type buttons and colored shapes sit in small blocks that the
        # broad pictograph ranges don't reach.
        for cp in (0x1F170, 0x1F171, 0x1F17E, 0x1F17F, 0x1F18E, 0x1F191, 0x1F19A,
                   0x1F7E0, 0x1F7EB, 0x1F7F0):
            self.assertTrue(is_known_emoji_base(cp), hex(cp))

    def test_neighbors_of_small_ranges_are_rejected(self):
        for cp in (0x1F172, 0x1F17D, 0x1F18F, 0x1F190, 0x1F19B, 0x1F7EC, 0x1F7F1):
            self.assertFalse(is_known_emoji_base(cp), hex(cp))

    def test_rejects_ordinary_text(self):
        self.assertFalse(is_known_emoji_base(ord("a")))
        self.assertFalse(is_known_emoji_base(ord("Z")))
        self.assertFalse(is_known_emoji_base(ord(" ")))

    def test_keycap_bases_are_known(self):
        for ch in "0123456789#*":
            self.assertTrue(is_known_emoji_base(ord(ch)), ch)


class SplitClustersTests(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(split_clusters(""), [])

    def test_single_emoji_is_one_cluster(self):
        self.assertEqual(split_clusters("🍕"), ["🍕"])

    def test_two_plain_emoji_back_to_back(self):
        self.assertEqual(split_clusters("🍕🍔"), ["🍕", "🍔"])

    def test_flag_stays_together_and_two_flags_split(self):
        self.assertEqual(split_clusters("🇨🇦🇺🇸"), ["🇨🇦", "🇺🇸"])

    def test_skin_tone_modifier_attaches_to_preceding_base(self):
        thumbs_up_toned = "\U0001F44D\U0001F3FD"
        self.assertEqual(split_clusters("🍕" + thumbs_up_toned), ["🍕", thumbs_up_toned])

    def test_zwj_sequence_is_one_cluster(self):
        family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"
        self.assertEqual(split_clusters(family + "🍕"), [family, "🍕"])

    def test_keycap_sequence_is_one_cluster(self):
        self.assertEqual(split_clusters("3️⃣🍕"), ["3️⃣", "🍕"])

    def test_lone_trailing_regional_indicator_is_its_own_cluster(self):
        lone = "\U0001F1E8"
        self.assertEqual(split_clusters(lone + "🍕"), [lone, "🍕"])


class AnalyzeAllTests(unittest.TestCase):
    def test_analyzes_each_cluster_independently(self):
        results = analyze_all("🍕🇨🇦")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].kind, "single_codepoint")
        self.assertEqual(results[1].kind, "flag_sequence")

    def test_empty_string_yields_no_analyses(self):
        self.assertEqual(analyze_all(""), [])


class FormatReportTests(unittest.TestCase):
    def test_json_output_round_trips(self):
        result = analyze("🍕")
        payload = json.loads(format_report(result, as_json=True))
        self.assertEqual(payload["kind"], "single_codepoint")
        self.assertEqual(payload["codepoint_count"], 1)
        self.assertEqual(payload["codepoints"][0]["codepoint"], "U+1F355")
        self.assertTrue(payload["codepoints"][0]["is_known_base"])

    def test_text_output_has_one_line_per_codepoint_plus_header(self):
        result = analyze("🇨🇦")
        text = format_report(result, as_json=False)
        self.assertEqual(len(text.splitlines()), 3)


class FlagSequenceTests(unittest.TestCase):
    def test_builds_canada_flag(self):
        self.assertEqual(flag_sequence("CA"), "🇨🇦")

    def test_lowercase_input_is_normalized(self):
        self.assertEqual(flag_sequence("ca"), flag_sequence("CA"))

    def test_round_trips_through_analyze(self):
        result = analyze(flag_sequence("US"))
        self.assertEqual(result.kind, "flag_sequence")
        self.assertEqual(len(result.codepoints), 2)

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            flag_sequence("USA")

    def test_rejects_non_alpha(self):
        with self.assertRaises(ValueError):
            flag_sequence("U1")


class TagSequenceTests(unittest.TestCase):
    def test_builds_england_flag(self):
        england = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
        self.assertEqual(tag_sequence("gbeng"), england)

    def test_round_trips_through_analyze(self):
        result = analyze(tag_sequence("gbsct"))
        self.assertEqual(result.kind, "tag_sequence")

    def test_round_trips_through_split_clusters(self):
        sequence = tag_sequence("gbwls")
        self.assertEqual(split_clusters(sequence + "🍕"), [sequence, "🍕"])

    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            tag_sequence("")

    def test_rejects_non_ascii_text(self):
        with self.assertRaises(ValueError):
            tag_sequence("gbéng")


if __name__ == "__main__":
    unittest.main()
