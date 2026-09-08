# emojiseq

An "emoji" you copy-paste is often not one character. A flag is two regional
indicator letters. A family emoji is four people joined by zero-width
joiners. A thumbs-up with a skin tone is a base character plus a Fitzpatrick
modifier appended after it. Two emoji that render identically can differ in
codepoint count, and a `len()` or string-equality check on emoji text will
happily lie to you.

`emojiseq` decomposes an emoji string into its codepoints, names each one,
and classifies the overall sequence shape (single codepoint, ZWJ sequence,
flag sequence, keycap sequence, skin-tone-modified emoji, or an unrecognized
multi-codepoint sequence). It's a library, not a CLI — the intent is to
call it from your own scripts, notebooks, or test suites.

Standard library only. No dependencies.

## Usage

```python
from emojiseq import analyze, format_report

result = analyze("🇨🇦")
print(result.kind)  # "flag_sequence"
print(len(result.codepoints))  # 2

# human-readable
print(format_report(result))
# '🇨🇦'  (flag_sequence, 2 codepoint(s))
#   U+1F1E8  regional_indicator    REGIONAL INDICATOR SYMBOL LETTER C
#   U+1F1E6  regional_indicator    REGIONAL INDICATOR SYMBOL LETTER A

# machine-readable, same data
print(format_report(result, as_json=True))
# {
#   "text": "🇨🇦",
#   "kind": "flag_sequence",
#   "codepoint_count": 2,
#   "codepoints": [
#     {"char": "🇨", "codepoint": "U+1F1E8", "name": "REGIONAL INDICATOR SYMBOL LETTER C", "role": "regional_indicator", "is_known_base": false},
#     {"char": "🇦", "codepoint": "U+1F1E6", "name": "REGIONAL INDICATOR SYMBOL LETTER A", "role": "regional_indicator", "is_known_base": false}
#   ]
# }
```

`format_report(analysis, as_json=True)` and the default text mode carry
exactly the same information, so scripts that need to pipe results
elsewhere and humans debugging in a REPL are both first-class.

You can also work with the structured result directly instead of the
rendered string:

```python
from emojiseq import analyze

family = analyze("\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466")
assert family.kind == "zwj_sequence"
for cp in family.codepoints:
    print(cp.codepoint, cp.role, cp.name)
```

### Strings with more than one emoji

`analyze` treats its whole input as a single sequence, so a string with
several emoji back to back (a sentence, a reaction bar, pasted chat text)
needs to be split into individual clusters first. `split_clusters` does
that, and `analyze_all` combines the split with `analyze` in one call:

```python
from emojiseq import analyze_all

for result in analyze_all("🍕🇨🇦👍🏽"):
    print(result.text, result.kind)
# 🍕 single_codepoint
# 🇨🇦 flag_sequence
# 👍🏽 modified_emoji
```

## What it recognizes

- **single_codepoint** — one base character, e.g. a plain pizza emoji.
- **zwj_sequence** — components joined by U+200D (families, professions,
  couples).
- **flag_sequence** — two REGIONAL INDICATOR SYMBOL LETTER codepoints.
- **tag_sequence** — a black flag followed by TAG characters and a tag
  terminator (used for England/Scotland/Wales-style subdivision flags).
- **keycap_sequence** — a digit or `#`/`*` followed by the keycap combiner.
- **modified_emoji** — a base emoji followed by a Fitzpatrick skin tone
  modifier.
- **not_emoji** — a single codepoint that isn't in a recognized emoji
  block, e.g. an ordinary letter.
- **multi_codepoint** — more than one codepoint that doesn't match any of
  the above (rare in well-formed emoji text, useful for catching mistakes).

Every `CodepointInfo` also carries `is_known_base`, which is `True` when
the codepoint falls in a block of Unicode known to contain emoji. This is
what separates `not_emoji` from `single_codepoint`:

```python
from emojiseq import analyze

analyze("a").kind     # "not_emoji"
analyze("🍕").kind    # "single_codepoint"
```

## Status

Classification covers the sequence shapes above, `split_clusters`/
`analyze_all` handle strings containing multiple emoji back to back, and
`is_known_emoji_base` distinguishes real emoji base characters from
ordinary text using a curated set of Unicode emoji block ranges. Those
ranges are hand-built from the block layout, not parsed from Unicode's
own `emoji-data.txt`/`emoji-sequences.txt`, so they'll miss a handful of
codepoints that are individually listed outside the main blocks. Loading
the official data files for exact fidelity is the next step.

## License

MIT, see [LICENSE](LICENSE).
