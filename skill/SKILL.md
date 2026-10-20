---
name: arabic-pdf-toolkit
description: Translate a PDF into Arabic in place (same layout, colours and images), write Arabic onto flattened pages, or handle Arabic text in PDFs (RTL, digits, units, extraction). Use for any English-to-Arabic PDF job.
---

# Arabic PDF toolkit

A single-file Python toolkit (`arpdf.py`, kept in the GitHub repository **WhisperShang/arabic-pdf-toolkit**) plus the workflow that goes with it. It was built on a real job: a 41-page, heavily designed nutrition plan translated into Egyptian Arabic with every photo, card, colour and table left intact.

**What it does:** it removes only the English text (images and vector art stay untouched) and typesets the Arabic in its place. It right-aligns each text box against the right edge of its original area. It moves bullets, step badges and emoji icons to the right-hand (RTL) side. It keeps chips, badges, running headers and avatar captions in sensible positions. It widens line spacing when the Arabic needs fewer lines, glues numbers to their units, and reports every box that had to shrink.

## Setup (once per session)

1. Get the code into the scratchpad (skip this if an `arpdf/` clone is already there):
   - `git clone --depth 1 https://github.com/WhisperShang/arabic-pdf-toolkit arpdf`
   - if the clone is refused because the repository is private, call the `add_repo` tool for `WhisperShang/arabic-pdf-toolkit` first (`access: "read"`, or `"push"` when you will improve the toolkit), then clone the way it says.
   - if GitHub can't be reached at all, tell the user the toolkit lives in that repository and ask them to attach `arpdf.py`.
2. `pip install --break-system-packages pymupdf fonttools` if needed (PyMuPDF ≥ 1.24).
3. `python3 arpdf/arpdf.py fonts --check` downloads the fonts into `arpdf/fonts` from github raw (Google Fonts), which the sandbox allows, and confirms which families copy and search correctly.

Font families (`family` in configs and overlays):

| family | font | use | copy/search |
|---|---|---|---|
| `sans` | IBM Plex Sans Arabic 400/500/600/700 | body text, UI | yes |
| `serif` | Markazi Text 400/700 (auto 1.2× size) | headings, serif source text | yes |
| `display` | El Messiri | titles, card headings | yes |
| `cairo` | Cairo 400/600/700 | geometric sans, Egyptian look | yes |
| `amiri` | Amiri | calligraphic headings | **no**: looks right, copies as garbage |

Only use `amiri` when looks matter more than copyable text, and say so. Amiri, Noto Naskh, Lateef, Scheherazade and Noto Sans Arabic all extract as garbage through MuPDF; Markazi, Plex, El Messiri, Cairo, Alexandria, Almarai and Tajawal extract correctly.

## Workflow: translate a PDF in place

1. **Inspect.** `arpdf.py inspect in.pdf` lists each page as `text`, `mixed` or `flattened`, plus a font catalog with the role guessed for each font. Pages with live text get replaced in place. Flattened pages (image only) go through the overlay workflow below. Only rebuild a page from scratch if neither works.
2. **Config (optional).** Defaults work without one. Write a config when you need to:
   - assign Type3 fonts to roles (Type3 fonts are unnamed, so `inspect` prints a skeleton);
   - keep text in English (logos, a gradient-filled title);
   - mirror nav bars or banners;
   - restore image-filled text.

   See *Config reference*.
3. **Samples first.** Pick 2–4 pages of different kinds (prose, table, cards, cover):
   - `extract in.pdf --pages 3,10,19 -o tr/p_sample.json`
   - fill in the `""` values and run `render in.pdf sample.pdf --pages 3,10,19 --tr tr --report rep.json`
   - `preview sample.pdf prev --compare in.pdf`, then **look at every image**
   - send the sample PDF and ask for comments on dialect, wording, digits, and what may stay English

   Only do the whole document after the user agrees.
4. **Whole document.** Extract in batches with `extract in.pdf --tr tr -o tr/pNN.json`, which writes only keys not yet translated, grouped by page. Then translate, render all pages, and read the report:
   - **missing:** no translation for that key.
   - **style-count:** the `§` counts differ between key and translation.
   - **scaled < 0.97:** the box shrank its text. Shorten the Arabic, or put a tighter version in a later file such as `tr/zz_fixes.json`; later files override earlier ones.

   Then re-render, run `preview out.pdf prev --mode pairs`, and view every page. Fix anything that overlaps or looks off, and repeat.
5. **Deliver** the PDF. Keep `tr/` and the config so follow-up edits only re-render.

Rendering takes about 2.5 s a page. For long documents run it in the background or by page range.

### Translation keys

- A key is one paragraph or bullet item of English, with line breaks joined.
- A `§` marks a change of colour or font inside the unit, for example `"Hello, Eyad,§this plan is yours"`. The Arabic must contain the same number of `§`, each placed where that style should switch: `"أهلاً يا إياد،§ الخطة دي بتاعتك"`.
- Bare numbers and quantities are handled automatically (`250 g` → `250 جم`). Write units in Arabic inside sentences too.
- Files are plain `{english: arabic}` JSON. Nested `{"p03": {...}}` objects, which is what `extract` writes, also load. Empty values are ignored.

## Translation style guide

- **Register.** Ask the user, or follow their preference: Egyptian colloquial (عشان، هتاكل، ماتنساش), formal Arabic (فصحى), or a natural mix. For a mix, use colloquial for coaching tone and formal Arabic for credentials and bios.
- **Digits.** Western (0–9) is the default in Egyptian print. Use `"digits": "arabic"` for ٠–٩.
- **Units.** جم، كجم، مجم، مل، لتر، سعر (kcal)، سم، دقيقة / دقايق، ساعة. Use `°م` for °C. Spoons can be shortened with `"replace": {"معلقة صغيرة": "م.ص", "معلقة كبيرة": "م.ك"}`.
- **What stays Latin.** Brand and device names (InBody, DE-FIT, GUC, EN & TPN) stay in Latin script, preceded by «الـ» where Arabic needs the article: «تحليل الـ InBody».
- **Names.** Write people's names in Arabic: Dr. Diaa Eldeen → د. ضياء الدين.
- **Local terms.** Prefer the local term over a transliteration: whole-wheat baladi → عيش بلدي سن، areesh → قريش، Roumi → رومي، turkey → ديك رومي.
- **Length.** Keep it about as long as the English, since boxes are fixed. Arabic usually comes out a little shorter; the toolkit widens line spacing to fill (up to 1.35×). When a box shrinks, shorten the wording rather than accepting small text.
- **Punctuation.** Use Arabic punctuation (، ؛ ؟ « »).

## Flattened pages: overlay

When a page is a picture of text, write a spec and run `overlay in.pdf spec.json out.pdf`. Each item's `rect` is painted with the sampled background colour (`"bg": "auto"`), or a hex colour, or `null` for none. The Arabic is then set inside the rect.

```json
{"pages": [{"page": 5, "items": [
  {"rect": [37, 70, 560, 102], "text": "خلّي طاقتك عالية", "family": "serif", "weight": 700,
   "size": 25, "color": "#2b1b33", "align": "right", "bg": "auto"},
  {"rect": [37, 104, 560, 172], "text": "…", "size": 11.6, "color": "#4a3d50", "line_height": 21}]}]}
```

To find the rects and colours, render the page with `preview` and measure it: 72 pt per inch, so at `--dpi 72` one pixel is one point. Use `--debug` to draw the boxes. This method only works on flat-coloured backgrounds; over photos, say it can't be done cleanly.

## Config reference

Unknown keys are ignored. Defaults are shown in `DEFAULT_CONFIG` in the source.

- **`roles`**: `{name: {"family", "weight" (number or "auto" = read from the source font name), "scale"}}`. The built-in roles are `body`, `serif`, `heading`, `strong`, `icon` (moved to the RTL start) and `keep` (never touched).
- **`font_rules`**: a list of `{"font": regex, "min_size", "max_size", "text": regex, "role"}`. The first matching rule wins. If nothing matches:
  - emoji become `icon`;
  - Type3 fonts become `heading` at 14 pt or more, and `strong` below that;
  - serif font names become `serif`;
  - everything else becomes `body`.
- **`keep`**: regexes on a unit's full text that leave it untouched.
- **`numeric_keep_max_size`** (8.6): bare numbers smaller than this, or inside boxes under 60 pt wide (badges), stay as they are. Other numbers are re-set right-aligned.
- **`left_align`**: `[{"pattern", "extend_to_container"}]` keeps matching units on the left edge, such as a chip at a card's top right. With `extend_to_container`, the box can run all the way to the container's right edge.
- **`side_bands`** ([35, 30]): text in the top and bottom bands (in points) keeps its side, which suits running headers and footers.
- **`margin`**: the page side margin in points. Detected automatically when unset.
- **`mirror_banners`**: words whose short bar gets its items mirrored left to right, e.g. `["BREAKFAST", "LUNCH"]`.
- **`mirror_regions`**: `[{"page", "y0", "y1"}]` mirrors units across the page within that band.
- **`restore_regions`**: `[{"page", "rect", "dpi"}]` re-stamps the original pixels on top, for gradient or image-filled text you are keeping.
- **`replace`**: Arabic string replacements applied at render time.
- **`digits`**: `"western"` or `"arabic"`.
- **`max_line_stretch`** (1.35) and **`scale_max_size`** (18): role scaling only applies below this size.

A tuned example, the config for the nutrition plan:

```json
{"roles": {"label": {"family": "amiri", "weight": 700, "scale": 1.12},
           "heading": {"family": "amiri", "weight": 700, "scale": 1.08},
           "card": {"family": "display", "weight": 700}},
 "font_rules": [{"font": "^Type3 \\((16|49|55) 0 R\\)$", "role": "label"},
                {"font": "^Type3 \\((78|84|91) 0 R\\)$", "role": "card"},
                {"font": "^Type3 \\((101|398) 0 R\\)$", "role": "keep"},
                {"font": "^Type3", "role": "heading"}],
 "keep": ["^(TWO-MEAL|PLAN)$"],
 "left_align": [{"pattern": "Loved it(?!:)", "extend_to_container": true}],
 "mirror_banners": ["BREAKFAST", "LUNCH", "BACKUP"],
 "mirror_regions": [{"page": 1, "y0": 600, "y1": 680}],
 "restore_regions": [{"page": 1, "rect": [36, 381, 560, 523], "dpi": 400}],
 "replace": {"معلقة صغيرة": "م.ص", "معلقة كبيرة": "م.ك"}}
```

## Other tools

- `text in.pdf [--pages] [--reverse]` prints a PDF's text. It maps Arabic presentation forms (ﺍﻟﻌﺮﺑﻴﺔ) back to normal letters, and `--reverse` undoes reversed, visual-order Arabic. Use it to read Arabic PDFs, and to confirm the output is searchable.
- `polish "نص"` shows the typography fixes and the invisible characters they insert.
- `preview pdf dir --mode pages|pairs|grid [--compare original.pdf]`.
- Python API (`import arpdf as A`):
  - `A.insert_arabic(page, rect, text, A.FontKit(), family, weight, size, color, align)` writes Arabic onto any page, including in brand-new PDFs.
  - `A.rtl_html(...)` builds the HTML for one RTL paragraph.
  - Text helpers: `A.polish`, `A.to_arabic_digits`, `A.to_western_digits`, `A.normalize_arabic` (for search and compare), `A.fix_presentation_forms`, `A.visual_to_logical`, `A.has_arabic`, `A.auto_quantity`.

## Gotchas

- Inside `dir="rtl"`, MuPDF's HTML engine swaps `text-align: left` and `right`. `rtl_html` handles this: RTL default for right-aligned text, and an LTR block wrapping an RTL run for text kept on the left. Don't hand-write `text-align` in RTL HTML.
- Table columns are not mirrored, on purpose: their dividers are drawn graphics. Cells are right-aligned in place.
- Text drawn with a gradient or image fill disappears from the text layer, or gets damaged, when nearby text is redacted. Keep it in English with `keep` and re-stamp it with `restore_regions`.
- Symbols missing from Arabic fonts (♥ ✓ ★) automatically fall back to DejaVu.
- Redaction removes text only (`images=0, graphics=0`), so photos and vector art underneath survive.

## Improving the toolkit

When the user asks for a change, or a job reveals a layout bug:

1. Attach the repository with push access (`add_repo`, `access: "push"`) and work in the clone.
2. Put document-specific behaviour in a config, not the code. A fix to the code needs a test:
   - extend `tests/make_fixture.py` and its translations in `tests/fixture/tr/`, which are invented and safe to commit;
   - or, if the user attaches a real job, add it under `tests/private/<name>/`, which is git-ignored and never committed.
3. Run `python3 tests/run_tests.py`.
   - If a reference image changed on purpose, view the new render, then run `--update-golden`.
   - Never use `--update-golden` to silence a failure you haven't looked at.
4. Keep the source free of `\u` escapes (write invisible characters with `chr()`); a test enforces it.
5. Commit with a clear message and push. Ask the user once whether they prefer pull requests or direct pushes to `main`.
6. If this file (`skill/SKILL.md` in the repo) changed, propose the updated skill with `propose_skills`, using the repo copy as the full text, so the saved skill and the repo stay identical.
