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


@dataclass(frozen=True)
class CodepointInfo:
    char: str
    codepoint: int
    name: str
    role: Role

    def to_dict(self) -> dict:
        return {
            "char": self.char,
            "codepoint": f"U+{self.codepoint:04X}",
            "name": self.name,
            "role": self.role.value,
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
    if len(codepoints) == 1:
        return "single_codepoint"
    return "multi_codepoint"


def analyze(text: str) -> SequenceAnalysis:
    """Break `text` into codepoints and classify the overall sequence shape."""
    codepoints = [
        CodepointInfo(
            char=ch,
            codepoint=ord(ch),
            name=_name_for(ch),
            role=_classify_codepoint(ord(ch)),
        )
        for ch in text
    ]
    return SequenceAnalysis(
        text=text,
        codepoints=tuple(codepoints),
        kind=_classify_sequence(codepoints),
    )


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
        lines.append(f"  U+{cp.codepoint:04X}  {cp.role.value:<20} {cp.name}")
    return "\n".join(lines)
