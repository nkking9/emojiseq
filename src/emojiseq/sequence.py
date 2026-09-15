"""Decompose emoji strings into codepoints and classify the sequence shape.

An "emoji" as typed or displayed is frequently not one codepoint. A flag is
two regional indicators, a family is five or more people joined by U+200D,
and a thumbs-up-with-skin-tone is a base character plus a Fitzpatrick
modifier. Treating these strings as opaque blobs makes it hard to tell why
two visually identical emoji compare unequal, or why a supposedly single
emoji is actually four graphemes stitched together. This module makes that
structure explicit.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Role(Enum):
    BASE = "base"
    ZWJ = "zwj"
    VARIATION_SELECTOR = "variation_selector"
    SKIN_TONE = "skin_tone"
    REGIONAL_INDICATOR = "regional_indicator"
    KEYCAP_COMBINER = "keycap_combiner"
    TAG = "tag"
    TAG_TERMINATOR = "tag_terminator"


ZERO_WIDTH_JOINER = "‍"
VARIATION_SELECTOR_16 = "️"
KEYCAP_COMBINER = "⃣"
TAG_TERMINATOR = "\U000e007f"

# Fitzpatrick skin tone modifiers, EMOJI MODIFIER FITZPATRICK TYPE-1-2..TYPE-6.
_SKIN_TONE_RANGE = range(0x1F3FB, 0x1F400)
# REGIONAL INDICATOR SYMBOL LETTER A..Z, used in pairs to spell flag codes.
_REGIONAL_INDICATOR_RANGE = range(0x1F1E6, 0x1F200)
# TAG characters used to spell subdivision flags, e.g. england/scotland/wales.
_TAG_RANGE = range(0xE0020, 0xE0080)

# Person codepoints that appear as ZWJ sequence components in family and
# couple sequences (not the modifier-bearing "person with X hair" variants,
# just the base human figures).
_PERSON_CODEPOINTS = frozenset({
    0x1F466,  # BOY
    0x1F467,  # GIRL
    0x1F468,  # MAN
    0x1F469,  # WOMAN
    0x1F9D1,  # ADULT
    0x1F9D2,  # CHILD
})
_HEAVY_BLACK_HEART = 0x2764
_KISS_MARK = 0x1F48B

# Base codepoints that can legitimately start or stand alone as an emoji,
# as opposed to a ZWJ/keycap/tag/skin-tone modifier that only ever attaches
# to one. This is a curated approximation of the ranges Unicode's own
# emoji-data.txt marks with the Emoji property, built by hand from the
# block layout rather than by parsing the actual file. It covers the
# blocks almost everything in day-to-day use comes from; it will miss a
# handful of individually-listed codepoints outside those blocks. Loading
# emoji-data.txt itself for exact fidelity is still on the list.
_EMOJI_BASE_RANGES: tuple[range, ...] = (
    range(0x0023, 0x0024),  # keycap base: #
    range(0x002A, 0x002B),  # keycap base: *
    range(0x0030, 0x003A),  # keycap base: 0-9
    range(0x00A9, 0x00AA),  # copyright
    range(0x00AE, 0x00AF),  # registered
    range(0x203C, 0x203D),  # double exclamation mark
    range(0x2049, 0x204A),  # exclamation question mark
    range(0x2122, 0x2123),  # trade mark
    range(0x2139, 0x213A),  # information
    range(0x2194, 0x21AB),  # arrows
    range(0x231A, 0x231C),  # watch, hourglass
    range(0x2328, 0x2329),  # keyboard
    range(0x23CF, 0x23D0),  # eject
    range(0x23E9, 0x23FB),  # media control symbols
    range(0x24C2, 0x24C3),  # circled M
    range(0x25AA, 0x25AC),  # small squares
    range(0x25B6, 0x25B7),  # play button
    range(0x25C0, 0x25C1),  # reverse button
    range(0x25FB, 0x2600),  # geometric shapes
    range(0x2600, 0x27C0),  # misc symbols + dingbats
    range(0x2934, 0x2936),  # arrow curving
    range(0x2B05, 0x2B08),  # arrows
    range(0x2B1B, 0x2B1D),  # squares
    range(0x2B50, 0x2B51),  # star
    range(0x2B55, 0x2B56),  # heavy circle
    range(0x3030, 0x3031),  # wavy dash
    range(0x303D, 0x303E),  # part alternation mark
    range(0x3297, 0x3298),  # japanese "congratulations" button
    range(0x3299, 0x329A),  # japanese "secret" button
    range(0x1F000, 0x1F0FF),  # mahjong tiles, playing cards
    range(0x1F200, 0x1F2FF),  # enclosed ideographic supplement
    range(0x1F300, 0x1F5FF),  # misc symbols and pictographs
    range(0x1F600, 0x1F64F),  # emoticons
    range(0x1F680, 0x1F6FF),  # transport and map symbols
    range(0x1F900, 0x1F9FF),  # supplemental symbols and pictographs
    range(0x1FA00, 0x1FAFF),  # symbols and pictographs extended-A
)


def is_known_emoji_base(cp: int) -> bool:
    """Return whether `cp` falls in a block known to contain base emoji.

    Structural codepoints (ZWJ, variation selectors, skin tones, regional
    indicators, keycap combiner, tags) are handled by `_classify_codepoint`
    and are not what this checks; this is specifically for the "can this
    stand on its own as an emoji" question, used to tell "🍕" apart from
    plain text like "a" that happens to be a single codepoint.
    """
    return any(cp in r for r in _EMOJI_BASE_RANGES)


@dataclass(frozen=True)
class CodepointInfo:
    char: str
    codepoint: int
    name: str
    role: Role
    is_known_base: bool

    def to_dict(self) -> dict:
        return {
            "char": self.char,
            "codepoint": f"U+{self.codepoint:04X}",
            "name": self.name,
            "role": self.role.value,
            "is_known_base": self.is_known_base,
        }


@dataclass(frozen=True)
class SequenceAnalysis:
    text: str
    codepoints: tuple[CodepointInfo, ...]
    kind: str

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "kind": self.kind,
            "codepoint_count": len(self.codepoints),
            "codepoints": [c.to_dict() for c in self.codepoints],
        }


def _classify_codepoint(cp: int) -> Role:
    if cp == ord(ZERO_WIDTH_JOINER):
        return Role.ZWJ
    if cp == ord(VARIATION_SELECTOR_16):
        return Role.VARIATION_SELECTOR
    if cp == ord(KEYCAP_COMBINER):
        return Role.KEYCAP_COMBINER
    if cp == ord(TAG_TERMINATOR):
        return Role.TAG_TERMINATOR
    if cp in _SKIN_TONE_RANGE:
        return Role.SKIN_TONE
    if cp in _REGIONAL_INDICATOR_RANGE:
        return Role.REGIONAL_INDICATOR
    if cp in _TAG_RANGE:
        return Role.TAG
    return Role.BASE


def _name_for(char: str) -> str:
    try:
        return unicodedata.name(char)
    except ValueError:
        # Control-ish codepoints (tags, some modifiers) have no Unicode name.
        return "UNNAMED"


def _classify_sequence(codepoints: list[CodepointInfo]) -> str:
    roles = [c.role for c in codepoints]
    if not roles:
        return "empty"
    if Role.ZWJ in roles:
        return "zwj_sequence"
    if roles.count(Role.REGIONAL_INDICATOR) >= 2:
        return "flag_sequence"
    if Role.TAG in roles and Role.TAG_TERMINATOR in roles:
        return "tag_sequence"
    if Role.KEYCAP_COMBINER in roles:
        return "keycap_sequence"
    if Role.SKIN_TONE in roles:
        return "modified_emoji"
    if roles == [Role.BASE, Role.VARIATION_SELECTOR]:
        return "variation_sequence"
    if len(codepoints) == 1:
        return "single_codepoint" if codepoints[0].is_known_base else "not_emoji"
    return "multi_codepoint"


def analyze(text: str) -> SequenceAnalysis:
    """Break `text` into codepoints and classify the overall sequence shape."""
    codepoints = [
        CodepointInfo(
            char=ch,
            codepoint=ord(ch),
            name=_name_for(ch),
            role=_classify_codepoint(ord(ch)),
            is_known_base=is_known_emoji_base(ord(ch)),
        )
        for ch in text
    ]
    return SequenceAnalysis(
        text=text,
        codepoints=tuple(codepoints),
        kind=_classify_sequence(codepoints),
    )


def describe(analysis: SequenceAnalysis) -> str | None:
    """Name the specific ZWJ sequence shape, e.g. "family", "couple", "profession".

    `analysis.kind` already says "zwj_sequence", but that covers dozens of
    visually and semantically different combinations. This narrows it down
    for the common cases built from person figures: two or more people
    joined directly is a family, two joined through a heart is a couple,
    a couple sequence that also carries a kiss mark is a kiss, and one
    person joined to a single non-person object (a microscope, a wrench,
    a laptop) is a profession. Returns None for non-ZWJ input and for ZWJ
    sequences that don't match one of those patterns, e.g. flag-adjacent
    ZWJ sequences with no person component at all.
    """
    if analysis.kind != "zwj_sequence":
        return None
    bases = [c.codepoint for c in analysis.codepoints if c.role == Role.BASE]
    if _KISS_MARK in bases:
        return "kiss"
    if _HEAVY_BLACK_HEART in bases:
        return "couple"
    if len(bases) >= 2 and all(cp in _PERSON_CODEPOINTS for cp in bases):
        return "family"
    if len(bases) == 2 and sum(cp in _PERSON_CODEPOINTS for cp in bases) == 1:
        return "profession"
    return None


def split_clusters(text: str) -> list[str]:
    """Split `text` into individual emoji clusters.

    `unicodedata` has no notion of grapheme-cluster boundaries, so this
    walks the codepoints itself using the same role classification as
    `analyze`: a ZWJ glues the base before and after it into one cluster,
    a regional indicator pairs with a lone preceding one to close a flag,
    and variation selectors / skin tones / tag characters / the keycap
    combiner always attach to whatever cluster precedes them. Anything
    else starts a new cluster.
    """
    clusters: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            clusters.append("".join(current))
            current.clear()

    for ch in text:
        role = _classify_codepoint(ord(ch))
        if role == Role.ZWJ:
            current.append(ch)
        elif role in (
            Role.VARIATION_SELECTOR,
            Role.SKIN_TONE,
            Role.TAG,
            Role.TAG_TERMINATOR,
            Role.KEYCAP_COMBINER,
        ):
            current.append(ch)
        elif role == Role.REGIONAL_INDICATOR:
            if len(current) == 1 and _classify_codepoint(ord(current[0])) == Role.REGIONAL_INDICATOR:
                current.append(ch)
                flush()
            else:
                flush()
                current.append(ch)
        else:  # BASE
            if current and current[-1] == ZERO_WIDTH_JOINER:
                current.append(ch)
            else:
                flush()
                current.append(ch)
    flush()
    return clusters


def analyze_all(text: str) -> list[SequenceAnalysis]:
    """Split `text` into clusters with `split_clusters` and analyze each one."""
    return [analyze(cluster) for cluster in split_clusters(text)]


def flag_sequence(region_code: str) -> str:
    """Build a regional-indicator flag sequence from a 2-letter region code.

    `flag_sequence("CA")` returns the same two codepoints as pasting the
    Canadian flag emoji: each ASCII letter is shifted into the regional
    indicator symbol block (U+1F1E6 = REGIONAL INDICATOR SYMBOL LETTER A).
    Raises ValueError if `region_code` isn't exactly two ASCII letters.
    """
    if len(region_code) != 2 or not region_code.isascii() or not region_code.isalpha():
        raise ValueError(f"flag_sequence requires a 2-letter ASCII code, got {region_code!r}")
    return "".join(chr(0x1F1E6 + (ord(c.upper()) - ord("A"))) for c in region_code)


def tag_sequence(text: str, base: str = "\U0001F3F4") -> str:
    """Build a tag sequence spelling `text`, e.g. subdivision flags.

    Subdivision flags like England/Scotland/Wales have no dedicated
    codepoint; they're spelled out with TAG characters that echo an ISO
    3166-2 code (e.g. "gbeng") after a black flag base, terminated by
    U+E007F. Each character of `text` must be printable ASCII in the
    range the tag block covers (U+0020-U+007E), since that's what maps
    onto TAG characters U+E0020-U+E007E.
    """
    if not text:
        raise ValueError("tag_sequence requires non-empty text")
    if not all(0x20 <= ord(c) <= 0x7E for c in text):
        raise ValueError(f"tag_sequence text must be printable ASCII, got {text!r}")
    tags = "".join(chr(0xE0000 + ord(c)) for c in text)
    return base + tags + TAG_TERMINATOR


def format_report(analysis: SequenceAnalysis, as_json: bool = False) -> str:
    """Render an analysis as either a JSON document or an aligned text table.

    Both modes carry the same information; JSON is for piping into other
    tools, the text table is for reading in a terminal while debugging.
    """
    if as_json:
        return json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2)

    header = f"{analysis.text!r}  ({analysis.kind}, {len(analysis.codepoints)} codepoint(s))"
    lines = [header]
    for cp in analysis.codepoints:
        flag = "" if cp.is_known_base or cp.role != Role.BASE else "  (not a known emoji base)"
        lines.append(f"  U+{cp.codepoint:04X}  {cp.role.value:<20} {cp.name}{flag}")
    return "\n".join(lines)
