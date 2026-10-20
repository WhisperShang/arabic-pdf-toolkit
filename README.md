# arabic-pdf-toolkit

Translate a PDF's English text into Arabic **in place**: same layout, colours, photos and vector art, with the Arabic typeset right-to-left where the English was. It also writes Arabic onto flattened (image-only) pages and handles the Arabic text details that make print look native: RTL boxes, contextual shaping, digits, units, and the no-break and bidi characters around numbers.

Built on a real job: a 41-page designed nutrition plan translated into Egyptian Arabic. Everything is one file, `arpdf.py` (PyMuPDF + fontTools).

## Quick start

```bash
git clone https://github.com/WhisperShang/arabic-pdf-toolkit && cd arabic-pdf-toolkit
pip install --break-system-packages pymupdf fonttools
python3 arpdf.py fonts --check                        # fetch fonts into ./fonts, verify copy/search
python3 arpdf.py inspect in.pdf                       # page kinds + font catalog
python3 arpdf.py extract in.pdf --tr tr -o tr/p01.json   # fill in the "" values
python3 arpdf.py render in.pdf out.pdf --tr tr --report issues.json
python3 arpdf.py preview out.pdf prev --compare in.pdf   # look at every page
```

| command | what it does |
|---|---|
| `fonts [--check]` | downloads IBM Plex Sans Arabic, Markazi Text, El Messiri, Cairo and Amiri; `--check` confirms which families copy and search correctly |
| `inspect` | labels each page `text`, `mixed` or `flattened`; font catalog with guessed roles; config skeleton for unnamed Type3 fonts |
| `extract` | untranslated text units as a fill-in JSON, grouped by page |
| `render` | removes the English text and typesets the Arabic; reports missing keys, style mismatches and shrunk boxes |
| `preview` | page PNGs, side-by-side pairs, a contact grid, or original-vs-new |
| `overlay` | paints and writes Arabic boxes from a JSON spec (for flattened pages) |
| `text` | extracts text, repairing presentation forms and visual-order Arabic |
| `polish` | shows the typography fixes on a string |

The full workflow, translation style guide and config reference are in [`skill/SKILL.md`](skill/SKILL.md). That file is also what Claude loads as the skill.

## Layout

```
arpdf.py                 the toolkit (CLI + importable module)
skill/SKILL.md           the Claude skill: workflow, style guide, config reference
examples/                example configs from real jobs
tests/make_fixture.py    builds tests/fixture/en.pdf, an invented document
tests/fixture/tr/        its Arabic translations
tests/golden/            reference renders of the fixture
tests/private/<name>/    your real documents (git-ignored): in.pdf, tr/, config.json, golden.pdf
tests/run_tests.py       the test runner
```

## Changing the code

1. Edit `arpdf.py`.
2. Run `python3 tests/run_tests.py`. It covers the unit checks, the font check, the fixture and every private suite.
3. If a reference image changed **on purpose** (a deliberate layout improvement), look at the new output and then run `python3 tests/run_tests.py --update-golden`.
4. Commit and push. The next session that uses the skill clones the latest version.

Rules worth keeping:
- **No `\u` escapes in the source.** Write invisible characters with `chr(0x...)`; a test enforces this.
- **Document quirks go in a config file**, not in the code (see `examples/`).
- **Add a test when you fix a layout bug.** Extend the fixture, or add a private suite for a real document.

### Private regression suites

Put a real job in `tests/private/<name>/`:
- `in.pdf`: the original;
- `tr/`: its translation files;
- `config.json`: optional;
- `golden.pdf`: the approved output, written by `--update-golden`.

The folder is git-ignored, so client documents never reach the repository. Keep a copy on your computer and attach it when you want Claude to run it.

## Known limits

- Amiri (and Noto Naskh, Lateef, Scheherazade) render correctly but copy as garbage through MuPDF. The default serif is Markazi Text, which extracts correctly.
- Table columns are not mirrored; cells are right-aligned in place.
- Overlays work on flat-coloured backgrounds only.
