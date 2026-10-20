#!/usr/bin/env python3
"""arpdf — Arabic PDF toolkit.

Translate a PDF's English text into Arabic *in place* (same layout, colours,
images), write Arabic onto flattened pages, and handle the Arabic text details
(RTL boxes, shaping, digits, units, bidi glue) that make output look native.

Subcommands (run `arpdf.py <cmd> -h` for options):
  fonts    download + prepare the Arabic font set
  inspect  per-page report (live text vs flattened) + font catalog + config skeleton
  extract  dump untranslated text units as a fill-in JSON, grouped by page
  render   rebuild the PDF with Arabic text from translation files
  preview  PNGs, side-by-side pairs, a contact grid, or original-vs-new comparison
  overlay  paint + write Arabic boxes from a JSON spec (for flattened pages)
  text     extract text, repairing Arabic presentation forms / visual order
  polish   apply Arabic typography fixes to a string (for testing)

Translation files: JSON dicts {english_key: arabic}. Empty values are ignored,
nested dicts are flattened (so extract's {"p03": {...}} output can be filled
in and used directly). A "§" in a key marks a style change (colour/weight)
inside one text unit; the Arabic must contain the same number of "§".
"""
import argparse, glob, html, json, os, re, shutil, statistics, subprocess, sys, unicodedata
import pymupdf

# ════════════════════════════════════════════════════════════════════════
# Fonts
# ════════════════════════════════════════════════════════════════════════
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONT_DOWNLOADS = {
    "IBMPlexSansArabic-Regular.ttf": GF + "ibmplexsansarabic/IBMPlexSansArabic-Regular.ttf",
    "IBMPlexSansArabic-Medium.ttf": GF + "ibmplexsansarabic/IBMPlexSansArabic-Medium.ttf",
    "IBMPlexSansArabic-SemiBold.ttf": GF + "ibmplexsansarabic/IBMPlexSansArabic-SemiBold.ttf",
    "IBMPlexSansArabic-Bold.ttf": GF + "ibmplexsansarabic/IBMPlexSansArabic-Bold.ttf",
    "Amiri-Regular.ttf": GF + "amiri/Amiri-Regular.ttf",
    "Amiri-Bold.ttf": GF + "amiri/Amiri-Bold.ttf",
    "ElMessiri-VF.ttf": GF + "elmessiri/ElMessiri%5Bwght%5D.ttf",
    "MarkaziText-VF.ttf": GF + "markazitext/MarkaziText%5Bwght%5D.ttf",
    "Cairo-VF.ttf": GF + "cairo/Cairo%5Bslnt,wght%5D.ttf",
}
FONT_INSTANCES = {  # static weights cut from variable fonts: name -> (source, axes)
    "ElMessiri-SemiBold.ttf": ("ElMessiri-VF.ttf", {"wght": 600}),
    "ElMessiri-Bold.ttf": ("ElMessiri-VF.ttf", {"wght": 700}),
    "MarkaziText-Regular.ttf": ("MarkaziText-VF.ttf", {"wght": 400}),
    "MarkaziText-Bold.ttf": ("MarkaziText-VF.ttf", {"wght": 700}),
    "Cairo-Regular.ttf": ("Cairo-VF.ttf", {"wght": 400, "slnt": 0}),
    "Cairo-SemiBold.ttf": ("Cairo-VF.ttf", {"wght": 600, "slnt": 0}),
    "Cairo-Bold.ttf": ("Cairo-VF.ttf", {"wght": 700, "slnt": 0}),
}
SYMBOL_FONT = "DejaVuSans-Bold.ttf"  # ♥ ✓ ★ … that Arabic fonts lack
# family -> weight -> file. pitch = default line pitch / size; lh = min line-height factor;
# adjust = size multiplier so the family matches Latin text optically; searchable = copy/paste and
# search give correct Arabic (MuPDF builds ToUnicode from the cmap; fonts whose contextual forms
# have no cmap entry, like Amiri / Noto Naskh, extract as garbage — verify with `fonts --check`).
FAMILIES = {
    "sans": {"files": {400: "IBMPlexSansArabic-Regular.ttf", 500: "IBMPlexSansArabic-Medium.ttf",
                       600: "IBMPlexSansArabic-SemiBold.ttf", 700: "IBMPlexSansArabic-Bold.ttf"},
             "pitch": 1.45, "lh": 1.0, "metric": 400, "adjust": 1.0, "searchable": True},
    "serif": {"files": {400: "MarkaziText-Regular.ttf", 700: "MarkaziText-Bold.ttf"},
              "pitch": 1.35, "lh": 0.92, "metric": 700, "adjust": 1.2, "searchable": True},
    "display": {"files": {400: "ElMessiri-SemiBold.ttf", 700: "ElMessiri-Bold.ttf"},
                "pitch": 1.35, "lh": 1.0, "metric": 700, "adjust": 1.0, "searchable": True},
    "cairo": {"files": {400: "Cairo-Regular.ttf", 600: "Cairo-SemiBold.ttf", 700: "Cairo-Bold.ttf"},
              "pitch": 1.45, "lh": 0.85, "metric": 400, "adjust": 0.92, "searchable": True},
    "amiri": {"files": {400: "Amiri-Regular.ttf", 700: "Amiri-Bold.ttf"},
              "pitch": 1.35, "lh": 0.92, "metric": 700, "adjust": 1.0, "searchable": False},
}
DEFAULT_FONTDIR = os.environ.get("ARPDF_FONTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"))


def ensure_fonts(fontdir=DEFAULT_FONTDIR, quiet=False):
    """Download/prepare every font the toolkit uses. Idempotent."""
    os.makedirs(fontdir, exist_ok=True)
    for name, url in FONT_DOWNLOADS.items():
        dst = os.path.join(fontdir, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 10000: continue
        if not quiet: print("download", name)
        subprocess.run(["curl", "-sSfL", "-o", dst, url], check=True)
    need = [n for n in FONT_INSTANCES if not os.path.exists(os.path.join(fontdir, n))]
    if need:
        try:
            from fontTools.ttLib import TTFont
            from fontTools.varLib import instancer
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "fonttools"], check=True)
            from fontTools.ttLib import TTFont
            from fontTools.varLib import instancer
        for n in need:
            vf, axes = FONT_INSTANCES[n]
            instancer.instantiateVariableFont(TTFont(os.path.join(fontdir, vf)), axes).save(os.path.join(fontdir, n))
            if not quiet: print("instance", n)
    sym = os.path.join(fontdir, SYMBOL_FONT)
    if not os.path.exists(sym):
        for cand in glob.glob("/usr/share/fonts/**/" + SYMBOL_FONT, recursive=True):
            shutil.copy(cand, sym); break
    return fontdir


def check_fonts(fontdir=DEFAULT_FONTDIR, sample="خطة تغذية شخصية لإياد بالجبنة 250 جم"):
    """Render a sample in every family/weight and confirm the text extracts back correctly."""
    kit = FontKit(fontdir)
    res = []
    for fam, spec in FAMILIES.items():
        for w in spec["files"]:
            d = pymupdf.open(); p = d.new_page()
            insert_arabic(p, (40, 40, 560, 120), sample, kit, fam, w, 14, do_polish=False)
            got = fix_presentation_forms(p.get_text()).split()
            res.append((fam, w, got == sample.split()))
    return res


def _css_weight(w):
    return {400: "normal", 700: "bold"}.get(w, str(w))


def nearest_weight(family, w):
    ws = FAMILIES[family]["files"].keys()
    return min(ws, key=lambda x: (abs(x - (w or 400)), -x))


def make_css(fontdir):
    out = []
    for fam, spec in FAMILIES.items():
        for w, f in spec["files"].items():
            if os.path.exists(os.path.join(fontdir, f)):
                out.append(f"@font-face{{font-family:{fam};font-weight:{_css_weight(w)};src:url({f})}}")
    out.append(f"@font-face{{font-family:sym;src:url({SYMBOL_FONT})}}")
    out.append("body{margin:0;padding:0}")
    return "\n".join(out)


class FontKit:
    """Archive + CSS + metrics for one font directory."""
    def __init__(self, fontdir=DEFAULT_FONTDIR):
        ensure_fonts(fontdir, quiet=True)
        self.dir = fontdir
        self.archive = pymupdf.Archive(fontdir)
        self.css = make_css(fontdir)
        self.metrics = {}
        for fam, spec in FAMILIES.items():
            f = pymupdf.Font(fontfile=os.path.join(fontdir, spec["files"][spec["metric"]]))
            self.metrics[fam] = (f.ascender, -f.descender)


# ════════════════════════════════════════════════════════════════════════
# Arabic text utilities
# ════════════════════════════════════════════════════════════════════════
def _cls(*ranges):  # regex character class from (lo, hi) code points; chr() keeps this file ASCII-safe
    return "[" + "".join(re.escape(chr(a)) + ("-" + re.escape(chr(b)) if b != a else "") for a, b in ranges) + "]"


ARABIC_RE = re.compile(_cls((0x600, 0x6FF), (0x750, 0x77F), (0x8A0, 0x8FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)))
DIACRITICS_RE = re.compile(_cls((0x610, 0x61A), (0x64B, 0x65F), (0x670, 0x670), (0x6D6, 0x6ED)))
NBSP, WJ, LRE, PDF_ = chr(0xA0), chr(0x2060), chr(0x202A), chr(0x202C)  # no-break space, word joiner, bidi embed
WESTERN, ARABIC_INDIC, PERSIAN = "0123456789", "٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹"
UNITS_EN_AR = {"g": "جم", "kg": "كجم", "mg": "مجم", "ml": "مل", "L": "لتر", "l": "لتر", "kcal": "سعر",
               "cal": "سعر", "cm": "سم", "mm": "مم", "km": "كم", "min": "دقيقة", "sec": "ثانية",
               "h": "ساعة", "tsp": "م.ص", "tbsp": "م.ك"}
AR_UNITS = "جم|كجم|مجم|مل|لتر|سعر|سم|مم|كم|دقيقة|دقايق|دقائق|ثانية|ساعة|ساعات|بيضات|بيضة|م\\.ص|م\\.ك|م\\b"
QTY_RE = re.compile(r"^(≈ ?)?([\d.,–½¼¾ ]+?) ?(" + "|".join(map(re.escape, UNITS_EN_AR)) + r")$")
NUMERIC_RE = re.compile(r"^[\s\d.,:%/–\-+]*$")
SYMBOL_RE = re.compile("(" + _cls((0x2600, 0x27BF), (0x2B00, 0x2BFF)) + ")")


def has_arabic(t):
    return bool(ARABIC_RE.search(t or ""))


def to_arabic_digits(t, separators=True):
    """123.5 -> ١٢٣٫٥ (decimal/thousands separators only between digits)."""
    if separators:
        t = re.sub(r"(?<=\d)\.(?=\d)", "٫", t)
        t = re.sub(r"(?<=\d),(?=\d)", "٬", t)
    return t.translate(str.maketrans(WESTERN, ARABIC_INDIC))


def to_western_digits(t):
    t = t.translate(str.maketrans(ARABIC_INDIC + PERSIAN, WESTERN * 2))
    return t.replace("٫", ".").replace("٬", ",")


def normalize_arabic(t, diacritics=True, tatweel=True, alef=True, ya=False, ta_marbuta=False):
    """Normalise for search/compare (not for display)."""
    t = fix_presentation_forms(t)
    if diacritics: t = DIACRITICS_RE.sub("", t)
    if tatweel: t = t.replace("ـ", "")
    if alef: t = re.sub("[إأآٱ]", "ا", t)
    if ya: t = t.replace("ى", "ي")
    if ta_marbuta: t = t.replace("ة", "ه")
    return t


def fix_presentation_forms(t):
    """Map Arabic presentation forms (common in extracted PDF text) back to base letters."""
    return "".join(unicodedata.normalize("NFKC", c) if 0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF else c
                   for c in t)


def visual_to_logical(line):
    """Undo visual-order extraction (whole line reversed) while keeping Latin/digit runs readable."""
    rev = line[::-1]
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9 .,:%/\-]*[A-Za-z0-9]|[A-Za-z0-9]", lambda m: m.group(0)[::-1], rev)


def polish(ar, replace=None, digits="western"):
    """Typography fixes for Arabic UI/print text.
    - glue numbers to their units / to ≈ / across ranges with no-break chars
    - keep mixed fractions (1½) left-to-right
    - optional replacements (e.g. long units -> abbreviations) and digit style
    """
    if not ar: return ar
    for a, b in (replace or {}).items(): ar = ar.replace(a, b)
    ar = re.sub(r"(?<![\d,.]–)(?<![\d,.]–\d)(?<![\d,.]–\d\d)(?<![\d,.]–\d,\d\d)(\d) (" + AR_UNITS + ")", "\\1" + NBSP + "\\2", ar)
    ar = re.sub(r"(\d) / ", "\\1" + NBSP + "/ ", ar)
    ar = re.sub(r"(\d)–(\d)", "\\1" + WJ + "–" + WJ + "\\2", ar)
    ar = re.sub(r"≈ (\d)", "≈" + NBSP + "\\1", ar)
    ar = re.sub(r"(\d+[½¼¾])", LRE + "\\1" + PDF_, ar)
    if digits == "arabic": ar = to_arabic_digits(ar)
    return ar


def auto_quantity(key):
    """'250 g' -> '250 جم', '≈ 39 g' -> '≈ 39 جم'. None if not a bare quantity."""
    m = QTY_RE.match(key.strip())
    return (m.group(1) or "") + m.group(2).strip() + " " + UNITS_EN_AR[m.group(3)] if m else None


def rtl_html(text, family="sans", weight=400, size=11, color="#000000", line_height=None, align="right",
             runs=None):
    """HTML for one RTL paragraph. runs=[(text, color_hex, family, weight), ...] for multi-style text.
    align: right (RTL start), left (kept at the left edge), center, justify."""
    lh = line_height or size * FAMILIES[family]["pitch"]
    if runs is None: runs = [(text, color, family, weight)]
    inner = "".join(
        f'<span style="color:{c};font-family:{f};font-weight:{_css_weight(nearest_weight(f, w))}">'
        + SYMBOL_RE.sub(r'<span style="font-family:sym">\1</span>', html.escape(t)) + "</span>"
        for t, c, f, w in runs)
    base = (f"font-family:{family};font-weight:{_css_weight(nearest_weight(family, weight))};"
            f"font-size:{size:.2f}pt;line-height:{lh:.2f}pt;")
    if align == "left":  # MuPDF mirrors left/right inside dir=rtl; embed RTL in an LTR block instead
        return f'<div dir="ltr" style="{base}text-align:left">&#x202B;{inner}&#x202C;</div>'
    extra = {"center": "text-align:center", "justify": "text-align:justify"}.get(align, "")
    return f'<div dir="rtl" style="{base}{extra}">{inner}</div>'


def insert_arabic(page, rect, text, kit, family="sans", weight=400, size=11, color="#000000",
                  align="right", line_height=None, runs=None, scale_low=0.55, do_polish=True):
    """Write Arabic into rect on any page. Returns (spare_height, scale) from insert_htmlbox."""
    if do_polish:
        text = polish(text)
        if runs: runs = [(polish(t), c, f, w) for t, c, f, w in runs]
    body = rtl_html(text, family, weight, size * FAMILIES[family].get("adjust", 1.0), color, line_height, align, runs)
    return page.insert_htmlbox(pymupdf.Rect(rect), body, css=kit.css, archive=kit.archive, scale_low=scale_low)


# ════════════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════════════
SERIF_NAMES = r"(?i)serif(?!.*sans)|times|georgia|garamond|playfair|cormorant|merriweather|lora|baskerville|didot|bodoni|minion|cambria|libre ?caslon"
DEFAULT_CONFIG = {
    # roles: what each kind of source text becomes. weight "auto" = read from the source font name
    "roles": {
        "body": {"family": "sans", "weight": "auto"},
        "serif": {"family": "serif", "weight": "auto", "scale": 1.08},
        "heading": {"family": "serif", "weight": 700, "scale": 1.08},
        "strong": {"family": "sans", "weight": 700},
    },
    # first matching rule wins; fields: font (regex on span font name), min_size, max_size, text (regex), role
    # special roles: "icon" (emoji-like graphics moved to the RTL start), "keep" (never touched)
    "font_rules": [],
    "type3_default": {"heading_min_size": 14, "large": "heading", "small": "strong"},
    "keep": [],                    # regexes on a unit's full text: leave untouched (logos, English titles…)
    "numeric_keep_max_size": 8.6,  # bare numbers smaller than this (or in tiny boxes) stay as-is
    "left_align": [],              # [{"pattern": regex, "extend_to_container": bool}] keep at the left edge
    "side_bands": [35, 30],        # top/bottom page bands (pt) whose text keeps its side (running header/footer)
    "margin": None,                # page side margin in pt; None = detect from the document
    "mirror_banners": [],          # words that mark a short bar whose items get mirrored left<->right
    "mirror_regions": [],          # [{"page": 1, "y0": 600, "y1": 680}] mirror units across the page
    "restore_regions": [],         # [{"page": 1, "rect": [x0,y0,x1,y1], "dpi": 400}] re-stamp original pixels
    "replace": {},                 # Arabic replacements applied at render (e.g. "معلقة صغيرة": "م.ص")
    "digits": "western",           # or "arabic" (٠١٢٣)
    "scale_max_size": 18,          # role "scale" only applies below this size
    "max_line_stretch": 1.35,      # widen line spacing up to this factor when Arabic needs fewer lines
}


def load_config(path=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        user = json.load(open(path, encoding="utf-8"))
        for k, v in user.items():
            if k == "roles": cfg["roles"].update(v)
            else: cfg[k] = v
    cfg["roles"].setdefault("icon", {"family": "icon"})
    cfg["roles"].setdefault("keep", {"family": "keep"})
    return cfg


def weight_from_name(name):
    n = name.lower()
    if re.search(r"black|heavy|extrabold|ultrabold", n): return 700
    if re.search(r"semibold|demibold", n): return 600
    if "bold" in n: return 700
    if "medium" in n: return 500
    return 400


def is_emoji(t):
    t = t.strip()
    return bool(t) and all(ord(c) >= 0x1F000 or c in (chr(0xFE0F), chr(0x200D)) for c in t)


class Roles:
    def __init__(self, cfg):
        self.cfg = cfg
        self.rules = [dict(r, _re=re.compile(r.get("font", ".*")), _tre=re.compile(r["text"]) if r.get("text") else None)
                      for r in cfg["font_rules"]]
        self.cache = {}

    def of(self, span):
        """-> (role_name, weight)"""
        f, size, text = span["font"], span["size"], span["text"]
        key = (f, round(size, 2), is_emoji(text), text if len(text) < 3 else "")
        if key in self.cache: return self.cache[key]
        role = None
        for r in self.rules:
            if not r["_re"].search(f): continue
            if "min_size" in r and size < r["min_size"]: continue
            if "max_size" in r and size > r["max_size"]: continue
            if r["_tre"] and not r["_tre"].search(text): continue
            role = r["role"]; break
        if role is None:
            if is_emoji(text): role = "icon"
            elif f.startswith("Type3"):
                t3 = self.cfg["type3_default"]
                role = t3["large"] if size >= t3["heading_min_size"] else t3["small"]
            elif re.search(SERIF_NAMES, f): role = "serif"
            else: role = "body"
        spec = self.cfg["roles"].get(role, {"family": "sans", "weight": "auto"})
        w = spec.get("weight", "auto")
        w = weight_from_name(f) if w == "auto" else w
        self.cache[key] = (role, w)
        return self.cache[key]

    def family(self, role):
        return self.cfg["roles"].get(role, {}).get("family", "sans")

    def scale(self, role, size):
        s = self.cfg["roles"].get(role, {}).get("scale", 1.0)
        return s if size <= self.cfg["scale_max_size"] else 1.0


# ════════════════════════════════════════════════════════════════════════
# Page analysis: spans -> segments (one line run) -> units (paragraphs) -> items (bullets)
# ════════════════════════════════════════════════════════════════════════
GAP = 6.0


def norm_span_text(t):
    """Collapse letter-spaced caps 'P E R F O R M' -> 'PERFORM'."""
    if re.fullmatch(r"(?:[A-Za-z\-] )+[A-Za-z\-]", t.strip()) and len(t.strip()) > 2:
        return t.strip().replace(" ", "")
    return t


def join_lines(ts):
    out = ""
    for t in ts:
        t = t.strip()
        if not out: out = t
        elif out.endswith("-") and not out.endswith(" -"): out += t
        else: out += " " + t
    return out


class Seg:
    def __init__(self, spans, roles):
        self.spans, self.roles = spans, roles
        self.bbox = pymupdf.Rect(spans[0]["bbox"])
        for s in spans[1:]: self.bbox |= pymupdf.Rect(s["bbox"])
        main = max(spans, key=lambda s: len(s["text"].strip()))
        self.role = roles.of(main)
        self.size = main["size"]
        self.baseline = main["origin"][1]

    @property
    def fam(self): return self.role[0]

    def text(self): return "".join(norm_span_text(s["text"]) for s in self.spans)


class Unit:
    def __init__(self, seg): self.lines = [seg]

    @property
    def bbox(self):
        r = pymupdf.Rect(self.lines[0].bbox)
        for l in self.lines[1:]: r |= l.bbox
        return r

    @property
    def fam(self): return self.lines[0].fam

    @property
    def size(self): return self.lines[0].size

    def plain(self): return join_lines([l.text() for l in self.lines])


def get_segments(page, roles):
    raw = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for l in b["lines"]:
            spans = [s for s in l["spans"] if s["text"] != ""]
            if not spans: continue
            cur = [spans[0]]
            for s in spans[1:]:
                prev = cur[-1]
                gap = s["bbox"][0] - prev["bbox"][2]
                fp, fs = roles.of(prev)[0], roles.of(s)[0]
                if (gap > 0.8 * max(prev["size"], s["size"]) or (prev["color"] != s["color"] and gap > 0.25 * s["size"])
                        or fp != fs or fp in ("icon", "keep")):
                    raw.append(Seg(cur, roles)); cur = [s]
                else:
                    cur.append(s)
            raw.append(Seg(cur, roles))
    raw = [s for s in raw if s.text().strip()]
    raw.sort(key=lambda s: (round(s.baseline), s.bbox.x0))
    out = []
    for s in raw:  # re-join runs a generator split on one baseline
        if out:
            p = out[-1]
            if (abs(p.baseline - s.baseline) < 1.0 and p.fam == s.fam and p.fam not in ("icon", "keep")
                    and 0 <= s.bbox.x0 - p.bbox.x1 < 0.8 * s.size):
                out[-1] = Seg(p.spans + s.spans, roles); continue
        out.append(s)
    return out


def containers(page):
    out = []
    for d in page.get_drawings():
        if d.get("fill") is None and not (d.get("color") is not None and d.get("type") == "s"): continue
        r = pymupdf.Rect(d["rect"])
        if r.width >= 14 and r.height >= 8: out.append(r)
    return out


def images(page):
    out = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"])
        if r.width > 0.9 * page.rect.width and r.height > 0.9 * page.rect.height: continue  # page background
        if info["width"] <= 4 or info["height"] <= 4: continue  # stretched 1-px gradients
        out.append(r)
    return out


def image_conts(page):
    return [(r & page.rect) + (3, 3, -3, -3) for r in images(page) if r.width >= 60 and r.height >= 40]


def small_marks(page):
    return [pymupdf.Rect(d["rect"]) for d in page.get_drawings()
            if 0 < d["rect"].width < 13 and 0 < d["rect"].height < 13]


def small_fills(page):
    return [pymupdf.Rect(d["rect"]) for d in page.get_drawings()
            if d.get("fill") is not None and 0 < d["rect"].width < 120 and 0 < d["rect"].height < 30]


def contain(rects, bb):
    best = None
    for r in rects:
        if r.x0 <= bb.x0 + 1 and r.y0 <= bb.y0 + 1 and r.x1 >= bb.x1 - 1 and r.y1 >= bb.y1 - 1:
            if best is None or r.get_area() < best.get_area(): best = r
    return best


def analyze(page, roles, cfg):
    segs = sorted(get_segments(page, roles), key=lambda s: (s.bbox.y0, s.bbox.x0))
    conts = containers(page) + image_conts(page)
    W, H = page.rect.width, page.rect.height
    pagebox = pymupdf.Rect(0, 0, W, H)
    units = []
    for s in segs:
        c = contain(conts, s.bbox) or pagebox
        placed = False
        if s.fam not in ("icon", "keep"):
            for u in reversed(units):
                last = u.lines[-1]
                if (u.fam == s.fam and abs(u.size - s.size) < 0.3 and abs(u.bbox.x0 - s.bbox.x0) < 2.5
                        and -2.5 <= s.bbox.y0 - last.bbox.y1 < 0.45 * s.size and abs(last.bbox.x0 - s.bbox.x0) < 1.5
                        and s.spans[0]["color"] in {sp["color"] for l in u.lines for sp in l.spans}
                        and (contain(conts, u.bbox) or pagebox) == c):
                    u.lines.append(s); placed = True; break
        if not placed: units.append(Unit(s))
    keep_res = [re.compile(k) for k in cfg["keep"]]
    for u in units:
        u.cont = contain(conts, u.bbox) or pagebox
        u.is_page = u.cont == pagebox or u.cont.width > W - 5
        t = u.plain().strip()
        u.icon = u.fam == "icon"
        u.keep = (u.fam == "keep"
                  or (not u.icon and bool(NUMERIC_RE.match(t))
                      and (u.size < cfg["numeric_keep_max_size"] or u.cont.width < 60))
                  or (len(t) == 1 and not t.isalnum() and not u.icon)
                  or any(k.search(t) for k in keep_res))
    return units


def grow(v):
    return 0 if len(v.lines) > 1 else min(0.25 * v.bbox.width, 12)


def layout(page, units, cfg, margin):
    """Decide each unit's Arabic box (L, R), alignment, bullets, moved icons."""
    W, H = page.rect.width, page.rect.height
    imgs, marks = images(page), small_marks(page)
    conts, fills = containers(page) + image_conts(page), small_fills(page)
    pno = page.number + 1
    top_band, bottom_band = cfg["side_bands"]
    left_rules = [(re.compile(r["pattern"]), r.get("extend_to_container", False)) for r in cfg["left_align"]]
    for u in units:
        if u.keep or u.icon: continue
        bb, c = u.bbox, u.cont
        members = [v for v in units if contain([c], v.bbox) is not None and not v.icon and v.bbox.x0 >= c.x0 - 1]
        if u.is_page:
            R = W - margin
        else:
            leftpad = max(4, min(min(v.bbox.x0 for v in members) - c.x0, 24))
            R = c.x1 - leftpad
        y0, y1 = bb.y0 + 1, bb.y1 - 1
        R = min(R, W - 20)
        u.Rbase = R
        obst = [pymupdf.Rect(v.bbox.x0 - (grow(v) if not (v.keep or v.icon) else 0), v.bbox.y0, v.bbox.x1, v.bbox.y1)
                for v in units if v is not u]
        obst += imgs + marks + [r for r in conts if r.width < 120 and r.height < 30 and not r.contains(bb)]
        obst += [r for r in fills if not r.contains(bb)]
        u.obst = obst
        for r in obst:
            if r.x0 >= bb.x1 - 14 and r.y1 > y0 and r.y0 < y1 and r.x0 < R + GAP:
                R = min(R, r.x0 - GAP)
        u.R = max(R, bb.x1)
        # left edge: Arabic grows leftwards from its right anchor, so reserve a little room
        Lmin = c.x0 + 3 if not u.is_page else 20
        for r in imgs:
            if r.x1 <= bb.x0 + 1 and r.y1 > y0 and r.y0 < y1: Lmin = max(Lmin, r.x1 + 8)
        for r in marks + [r for r in conts if not r.contains(bb)] + fills:
            if r.x1 <= bb.x0 + 1 and r.y1 > y0 and r.y0 < y1: Lmin = max(Lmin, r.x1 + 3)
        for v in units:
            if v is not u and v.bbox.x1 <= bb.x0 + 1 and v.bbox.y1 > y0 and v.bbox.y0 < y1:
                Lmin = max(Lmin, v.bbox.x1 + 3)
        u.L = min(bb.x0, max(Lmin, bb.x0 - grow(u)))
        floor = (c.y1 - 3) if not u.is_page else H - 45
        for r in [v.bbox for v in units if v is not u] + imgs:
            if r.y0 >= bb.y1 - 1 and r.x1 > u.L and r.x0 < u.R: floor = min(floor, r.y0 - 1)
        u.floor = max(floor, bb.y1)
        # alignment
        t = u.plain()
        u.align, u.mirrored = "right", False
        if not u.is_page and c.width < 90 and c.height < 22:  # chip / badge / tag
            u.align = "center"; u.L, u.R = c.x0 + 1, c.x1 - 1
        elif bb.y1 < top_band or bb.y0 > H - bottom_band:  # running header/footer keeps its side
            u.align = "left"
        elif (abs((bb.x0 + bb.x1) / 2 - (c.x0 + c.x1) / 2) < 3 and bb.width < 0.85 * c.width and bb.x0 - c.x0 > 30
              and (u.is_page or c.width < 300) and not any(v.icon and abs(v.bbox.y0 - bb.y0) < 4 for v in units)):
            u.align = "center"; u.L, u.R = 2 * ((c.x0 + c.x1) / 2) - (c.x1 - 12), c.x1 - 12
        for rx, extend in left_rules:
            if rx.search(t):
                u.align = "left"
                if extend: u.R = c.x1 - 4
                else: u.L = bb.x0
        for r in imgs:  # caption next to a small avatar/photo hugs it
            if r.width < 80 and r.height < 80 and 0 <= bb.x0 - r.x1 < 25 and r.y1 > bb.y0 and r.y0 < bb.y1:
                u.align = "left"; u.L = bb.x0
                if u.is_page: u.R = max(u.R, bb.x0 + 160)
        for mr in cfg["mirror_regions"]:
            if mr["page"] == pno and mr["y0"] < bb.y0 < mr["y1"]:
                u.L, u.R = W - u.R, W - bb.x0; u.mirrored = True
        u.moved_icon = None  # icon just left of the text moves to the RTL start
        for v in units:
            if v.icon and abs(v.bbox.y0 - bb.y0) < 4 and 0 <= bb.x0 - v.bbox.x1 < 8:
                u.moved_icon = v; u.L = v.bbox.x0
    if cfg["mirror_banners"]:
        words = set(cfg["mirror_banners"])
        for c in {id(u.cont): u.cont for u in units}.values():
            inside = [u for u in units if u.cont == c and not (u.keep or u.icon)]
            if c.height < 45 and any(u.plain().strip() in words for u in inside):
                mid = c.x0 + c.x1
                for u in inside:
                    u.L, u.R = mid - u.R, mid - u.bbox.x0; u.mirrored = True
    # bullets / numbered badges: each belongs to the unit it sits beside; it splits the unit into items
    live = [u for u in units if not (u.keep or u.icon)]
    cand = marks + [v.bbox for v in units if v.keep and v.size < 7.5]
    owner = {}
    for m in cand:
        best, bd = None, 1e9
        for u in live:
            bb = u.bbox
            if not (m.y1 > bb.y0 and m.y0 < bb.y1): continue
            if bb.x1 - 2 <= m.x0 <= u.R + GAP + 18:
                dist = m.x0 - bb.x1
            elif bb.x0 - 20 <= m.x1 <= bb.x0 + 1 and not any(
                    v is not u and v.bbox.x1 <= m.x0 + 1 and m.x0 - v.bbox.x1 < 40
                    and v.bbox.y1 > m.y0 - 4 and v.bbox.y0 < m.y1 + 4 for v in live):
                dist = 1000 + (bb.x0 - m.x1)
            else:
                continue
            if dist < bd: best, bd = u, dist
        if best is not None: owner.setdefault(id(best), []).append(m)
    for u in live:
        mk = owner.get(id(u), [])
        # markers on the LTR side (bullets, numbered badges) move to the RTL side as one picture each,
        # unless the unit itself stays on the left (then its checkbox/marker stays with it)
        left = [pymupdf.Rect(m) for m in mk if m.x1 <= u.bbox.x0 + 1] if (u.align == "right" and not u.mirrored) else []
        clusters = []
        for m in sorted(left, key=lambda r: r.get_area(), reverse=True):
            for c in clusters:
                if c.intersects(m): c |= m; break
            else: clusters.append(m)
        u.left_marks = clusters
        starts = set()
        for m in mk:
            for k, ln in enumerate(u.lines):
                if m.y0 - 3 <= (ln.bbox.y0 + ln.bbox.y1) / 2 <= m.y1 + 3: starts.add(k); break
        items = []
        for k, ln in enumerate(u.lines):
            if not items or (k in starts and len(mk) > 1): items.append([ln])
            else: items[-1].append(ln)
        u.items = items
    return units


def item_key(lines, roles):
    """Translation key for an item; '§' separates runs with different colour/role."""
    runs = []
    for li, ln in enumerate(lines):
        for s in ln.spans:
            st = (s["color"], roles.of(s))
            t = norm_span_text(s["text"])
            if li > 0 and s is ln.spans[0]:
                prev = runs[-1][1] if runs else ""
                t = t.lstrip() if (prev.endswith("-") and not prev.endswith(" -")) else " " + t.lstrip()
            if runs and runs[-1][0] == st: runs[-1] = (st, runs[-1][1] + t)
            else: runs.append((st, t))
    merged = []
    for st, t in runs:
        if merged and (not t.strip() or st == merged[-1][0]): merged[-1] = (merged[-1][0], merged[-1][1] + t)
        else: merged.append((st, t))
    key = "§".join(re.sub(r"\s+", " ", t).strip() if i == 0 else re.sub(r"\s+", " ", t) for i, (st, t) in enumerate(merged))
    key = re.sub(r"\s+", " ", key).strip().replace(" §", "§ ").replace("§ ", "§").strip()
    return key, [st for st, t in merged]


def detect_margin(doc, cfg):
    if cfg.get("margin") is not None: return cfg["margin"]
    xs = []
    for p in doc:
        lines = [l["bbox"] for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"]
                 if l["bbox"][2] - l["bbox"][0] > 50]
        if lines: xs.append(min(b[0] for b in lines))
    return round(statistics.median(xs)) if xs else 36


# ════════════════════════════════════════════════════════════════════════
# Translation store
# ════════════════════════════════════════════════════════════════════════
def load_translations(paths):
    out = {}
    def add(d):
        for k, v in d.items():
            if isinstance(v, dict) and "ar" not in v: add(v)
            elif isinstance(v, dict):
                if v.get("ar"): out[k] = v["ar"]
            elif isinstance(v, str) and v.strip() and not k.startswith("_"): out[k] = v
    for p in paths or []:
        files = sorted(glob.glob(os.path.join(p, "*.json"))) if os.path.isdir(p) else [p]
        for f in files:
            if os.path.exists(f): add(json.load(open(f, encoding="utf-8")))
    return out


def parse_pages(arg, n):
    if not arg or arg == "all": return list(range(n))
    out = []
    for part in arg.split(","):
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a) - 1, int(b)))
        else: out.append(int(part) - 1)
    return [p for p in out if 0 <= p < n]


def iter_items(doc, pages, cfg):
    roles = Roles(cfg)
    margin = detect_margin(doc, cfg)
    for pn in pages:
        page = doc[pn]
        units = layout(page, analyze(page, roles, cfg), cfg, margin)
        yield pn, page, units, roles


def extract(src, cfg, tr, pages):
    """-> {"p03": {key: ""}, ...} for every untranslated unit."""
    doc = pymupdf.open(src)
    out = {}
    for pn, page, units, roles in iter_items(doc, parse_pages(pages, doc.page_count), cfg):
        for u in units:
            if u.keep or u.icon: continue
            for it in u.items:
                k, _ = item_key(it, roles)
                if k in tr or NUMERIC_RE.match(k.replace("§", "")) or auto_quantity(k): continue
                if any(k in d for d in out.values()): continue
                out.setdefault(f"p{pn + 1:02d}", {})[k] = ""
    return out


# ════════════════════════════════════════════════════════════════════════
# Render
# ════════════════════════════════════════════════════════════════════════
def hexcol(c): return "#%06x" % c


def render(src, out, tr, cfg, pages=None, fontdir=DEFAULT_FONTDIR, debug=False, log=print):
    """Rebuild `pages` of src with Arabic. Returns issues [{page, type, key, scale?}]."""
    kit = FontKit(fontdir)
    sdoc = pymupdf.open(src)
    doc, scratch = pymupdf.open(), pymupdf.open()
    issues = []
    sel = parse_pages(pages, sdoc.page_count)
    for pn, opage, units, roles in iter_items(sdoc, sel, cfg):
        doc.insert_pdf(sdoc, from_page=pn, to_page=pn)
        page = doc[-1]
        snaps = {id(u): opage.get_pixmap(clip=u.moved_icon.bbox, dpi=600, alpha=False)
                 for u in units if getattr(u, "moved_icon", None) is not None}
        moved = {id(u.moved_icon) for u in units if getattr(u, "moved_icon", None) is not None}
        # 1. remove the English (text only; images and vector art untouched)
        for u in units:
            if u.keep or (u.icon and id(u) not in moved): continue
            for ln in u.lines:
                for s in ln.spans:
                    r = pymupdf.Rect(s["bbox"]); h = r.height
                    r.y0 += h * 0.28; r.y1 -= h * 0.28
                    page.add_redact_annot(r, fill=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        # 2. write the Arabic
        for u in units:
            if u.keep or u.icon: continue
            fam = roles.family(u.fam)
            size = u.size * roles.scale(u.fam, u.size) * FAMILIES[fam].get("adjust", 1.0)
            pitch = (statistics.median(b.baseline - a.baseline for a, b in zip(u.lines, u.lines[1:]))
                     if len(u.lines) > 1 else u.size * FAMILIES[fam]["pitch"])
            asc, desc = kit.metrics[fam]
            lh = max(pitch, size * (asc + desc) * FAMILIES[fam]["lh"])
            R, L, rshift = u.R, u.L, 0
            if u.left_marks:  # bullets / numbered badges on the LTR side move to the RTL side
                mw = max(m.width for m in u.left_marks)
                for m in u.left_marks:
                    snap = opage.get_pixmap(clip=m, dpi=400, alpha=False)
                    page.draw_rect(m + (-1, -1, 1, 1), color=None, fill=sample_bg(opage, m + (-1.5, -1.5, 1.5, 1.5)), overlay=True)
                    x1 = R - (mw - m.width) / 2
                    page.insert_image(pymupdf.Rect(x1 - m.width, m.y0, x1, m.y1), pixmap=snap)
                rshift = mw + 7; R -= rshift
            icon_pix = snaps.get(id(u))
            if icon_pix is not None:
                ib = u.moved_icon.bbox
                page.insert_image(pymupdf.Rect(R - ib.width, ib.y0, R, ib.y1), pixmap=icon_pix)
                R -= ib.width + 3
            for ii, it in enumerate(u.items):
                key, styles = item_key(it, roles)
                ar = tr.get(key) or auto_quantity(key)
                if ar is None and NUMERIC_RE.match(key.replace("§", "")):
                    ar = key.replace("§", "").replace(" %", "%"); styles = styles[:1]
                if ar is None:
                    issues.append({"page": pn + 1, "type": "missing", "key": key}); ar = key
                else:
                    ar = polish(ar, cfg["replace"], cfg["digits"])
                parts = ar.split("§")
                if len(parts) != len(styles):
                    if len(styles) > 1: issues.append({"page": pn + 1, "type": "style-count", "key": key})
                    parts, styles = [ar.replace("§", "")], styles[:1]
                base_top = it[0].baseline - (lh - (asc + desc) * size) / 2 - asc * size
                if ii + 1 < len(u.items):
                    nxt = u.items[ii + 1][0]
                    bottom = nxt.baseline - (lh - (asc + desc) * size) / 2 - asc * size
                elif (len(u.lines) == 1 and fam != "sans") or u.align == "center":
                    bottom = base_top + lh * 1.08
                else:
                    bottom = max(u.floor, base_top + lh * len(it)) + lh * 0.25
                bottom = max(bottom, base_top + lh * 1.02)
                runs = []
                for (col, role), txt in zip(styles, parts):
                    rf = roles.family(role[0]) if role[0] not in ("icon", "keep") else fam
                    runs.append((txt, hexcol(col), rf, role[1] or 400))
                body = rtl_html("", fam, styles[0][1][1] or 400, size, line_height=lh, align=u.align, runs=runs)
                Ri = R
                if len(u.items) > 1 and u.align == "right" and not u.mirrored and icon_pix is None:
                    ib = pymupdf.Rect(it[0].bbox)
                    for l2 in it[1:]: ib |= l2.bbox
                    Ri = u.Rbase
                    for r in u.obst:
                        if r.x0 >= ib.x1 - 14 and r.y1 > ib.y0 + 1 and r.y0 < ib.y1 - 1 and r.x0 < Ri + GAP:
                            Ri = min(Ri, r.x0 - GAP)
                    Ri = max(Ri, ib.x1) - rshift
                if len(it) >= 2 and u.align != "center":  # fewer Arabic lines -> open up the spacing
                    tmp = scratch.new_page(width=page.rect.width, height=2000)
                    spare, _ = tmp.insert_htmlbox(pymupdf.Rect(L, 0, Ri, 1900), body, css=kit.css, archive=kit.archive)
                    scratch.delete_page(-1)
                    used = round((1900 - spare) / lh)
                    if 2 <= used < len(it):
                        lh2 = min(lh * len(it) / used, lh * cfg["max_line_stretch"])
                        body = body.replace(f"line-height:{lh:.2f}pt", f"line-height:{lh2:.2f}pt")
                        base_top = it[0].baseline - (lh2 - (asc + desc) * size) / 2 - asc * size
                        bottom = max(bottom, base_top + lh2 * used + 1)
                box = pymupdf.Rect(L, base_top, Ri, bottom)
                spare, scale = page.insert_htmlbox(box, body, css=kit.css, archive=kit.archive, scale_low=0.55)
                if debug: page.draw_rect(box, color=(1, 0, 0), width=0.4)
                if spare < 0: issues.append({"page": pn + 1, "type": "overflow", "key": key})
                elif scale < 0.97: issues.append({"page": pn + 1, "type": "scaled", "scale": round(scale, 2), "key": key})
        for rr in cfg["restore_regions"]:
            if rr["page"] == pn + 1:
                clip = pymupdf.Rect(rr["rect"])
                page.insert_image(clip, pixmap=opage.get_pixmap(clip=clip, dpi=rr.get("dpi", 300)))
    save_compact(doc, out)
    return issues


def save_compact(doc, out):
    tmp = out + ".tmp"
    doc.save(tmp, garbage=4, deflate=True)
    d2 = pymupdf.open(tmp); d2.subset_fonts(); d2.save(out, garbage=4, deflate=True); d2.close()
    os.remove(tmp)


# ════════════════════════════════════════════════════════════════════════
# Flattened pages: overlay boxes
# ════════════════════════════════════════════════════════════════════════
def sample_bg(page, rect, dpi=72):
    """Median colour of the rect's border pixels (for painting over flattened text)."""
    pix = page.get_pixmap(clip=rect, dpi=dpi, alpha=False)
    w, h = pix.width, pix.height
    pts = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    cols = sorted(pix.pixel(x, y)[:3] for x, y in pts)
    r, g, b = cols[len(cols) // 2]
    return (r / 255, g / 255, b / 255)


def overlay(src, spec, out, fontdir=DEFAULT_FONTDIR, debug=False):
    """spec: {"pages": [{"page": 5, "items": [{"rect": [x0,y0,x1,y1], "text": "…", "family": "sans",
    "weight": 400, "size": 11, "color": "#333333", "align": "right", "bg": "auto"|"#ffffff"|null,
    "line_height": null, "redact": false}]}]}. Pages not listed are copied unchanged."""
    kit = FontKit(fontdir)
    doc = pymupdf.open(src)
    issues = []
    for pg in spec["pages"]:
        page = doc[pg["page"] - 1]
        for it in pg["items"]:
            rect = pymupdf.Rect(it["rect"])
            if it.get("redact"):
                page.add_redact_annot(rect, fill=False); page.apply_redactions(images=0, graphics=0)
            bg = it.get("bg", "auto")
            if bg:
                col = sample_bg(page, rect) if bg == "auto" else tuple(int(bg[i:i + 2], 16) / 255 for i in (1, 3, 5))
                page.draw_rect(rect, color=None, fill=col, overlay=True)
            spare, scale = insert_arabic(page, rect, it["text"], kit, it.get("family", "sans"), it.get("weight", 400),
                                         it.get("size", 11), it.get("color", "#000000"), it.get("align", "right"),
                                         it.get("line_height"))
            if debug: page.draw_rect(rect, color=(1, 0, 0), width=0.4)
            if spare < 0 or scale < 0.97:
                issues.append({"page": pg["page"], "scale": round(scale, 2), "text": it["text"][:40]})
    save_compact(doc, out)
    return issues


# ════════════════════════════════════════════════════════════════════════
# Inspect / preview / text
# ════════════════════════════════════════════════════════════════════════
def inspect_pdf(src, cfg):
    doc = pymupdf.open(src)
    roles = Roles(cfg)
    pages, fonts = [], {}
    for p in doc:
        d = p.get_text("dict")
        chars = sum(len(s["text"].strip()) for b in d["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"])
        ar = sum(1 for b in d["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"] if has_arabic(s["text"]))
        area = sum((pymupdf.Rect(i["bbox"]) & p.rect).get_area() for i in p.get_image_info())
        cover = min(1.0, area / p.rect.get_area())
        kind = "flattened" if chars < 30 and cover > 0.5 else ("mixed" if cover > 0.6 else "text")
        pages.append({"page": p.number + 1, "chars": chars, "arabic_spans": ar, "image_cover": round(cover, 2), "kind": kind})
        for b in d["blocks"]:
            if b["type"]: continue
            for l in b["lines"]:
                for s in l["spans"]:
                    f = fonts.setdefault(s["font"], {"spans": 0, "sizes": set(), "colors": {}, "samples": [], "pages": set()})
                    f["spans"] += 1; f["sizes"].add(round(s["size"], 1)); f["pages"].add(p.number + 1)
                    f["colors"][hexcol(s["color"])] = f["colors"].get(hexcol(s["color"]), 0) + 1
                    t = s["text"].strip()
                    if len(t) > 1 and len(f["samples"]) < 3 and t not in f["samples"]: f["samples"].append(t[:40])
                    f["role"] = roles.of(s)[0]
    cat = []
    for name, f in sorted(fonts.items(), key=lambda kv: -kv[1]["spans"]):
        cat.append({"font": name, "spans": f["spans"], "sizes": sorted(f["sizes"])[:6],
                    "colors": sorted(f["colors"], key=lambda c: -f["colors"][c])[:3],
                    "pages": sorted(f["pages"])[:10], "samples": f["samples"], "guessed_role": f["role"]})
    skeleton = {"font_rules": [{"font": "^" + c["font"].replace("(", "\\(").replace(")", "\\)") + "$", "role": c["guessed_role"]}
                               for c in cat if c["font"].startswith("Type3")]}
    return {"pages": pages, "fonts": cat, "config_skeleton": skeleton}


def _paste(pixes, cols, gap=10):
    rows = (len(pixes) + cols - 1) // cols
    cw = max(p.width for p in pixes); ch = max(p.height for p in pixes)
    out = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, cols * cw + (cols - 1) * gap, rows * ch + (rows - 1) * gap), False)
    out.clear_with(255)
    for k, p in enumerate(pixes):
        if p.alpha or p.n != 3: p = pymupdf.Pixmap(pymupdf.csRGB, p, 0) if p.n != 3 else pymupdf.Pixmap(p, 0)
        p.set_origin((k % cols) * (cw + gap), (k // cols) * (ch + gap)); out.copy(p, p.irect)
    return out


def preview(pdf, out_dir, pages=None, dpi=95, mode="pages", compare=None, cols=3):
    """mode: pages | pairs | grid. compare=original.pdf -> original|new per page
    (page numbers in `pages` refer to the new file; with compare they map 1:1 by order)."""
    os.makedirs(out_dir, exist_ok=True)
    doc = pymupdf.open(pdf)
    sel = parse_pages(pages, doc.page_count)
    written = []
    if compare:
        odoc = pymupdf.open(compare)
        osel = parse_pages(pages, odoc.page_count) if len(odoc) != len(doc) or pages else sel
        for k, pn in enumerate(sel):
            on = osel[k] if k < len(osel) else pn
            img = _paste([odoc[on].get_pixmap(dpi=dpi), doc[pn].get_pixmap(dpi=dpi)], 2)
            f = os.path.join(out_dir, f"compare_{on + 1:02d}.png"); img.save(f); written.append(f)
        return written
    pix = [doc[pn].get_pixmap(dpi=dpi) for pn in sel]
    if mode == "pages":
        for pn, p in zip(sel, pix):
            f = os.path.join(out_dir, f"page_{pn + 1:02d}.png"); p.save(f); written.append(f)
    elif mode == "pairs":
        for k in range(0, len(pix), 2):
            f = os.path.join(out_dir, f"pair_{sel[k] + 1:02d}.png"); _paste(pix[k:k + 2], 2).save(f); written.append(f)
    else:
        f = os.path.join(out_dir, "grid.png"); _paste(pix, cols).save(f); written.append(f)
    return written


def dump_text(pdf, pages=None, fix=True, reverse=False):
    doc = pymupdf.open(pdf)
    out = []
    for pn in parse_pages(pages, doc.page_count):
        t = doc[pn].get_text("text")
        if fix: t = fix_presentation_forms(t)
        if reverse: t = "\n".join(visual_to_logical(l) if has_arabic(l) else l for l in t.splitlines())
        out.append(f"===== page {pn + 1} =====\n{t}")
    return "\n".join(out)


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════
def main(argv=None):
    ap = argparse.ArgumentParser(prog="arpdf", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fonts", default=DEFAULT_FONTDIR, help="font directory (default: ./fonts next to arpdf.py or $ARPDF_FONTS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fonts", help="download/prepare fonts")
    s.add_argument("--check", action="store_true", help="also verify each family extracts as correct text")
    s = sub.add_parser("inspect", help="page kinds + font catalog + config skeleton")
    s.add_argument("pdf"); s.add_argument("--config"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("extract", help="untranslated keys as fill-in JSON")
    s.add_argument("pdf"); s.add_argument("-o", "--out"); s.add_argument("--tr", nargs="*", default=[])
    s.add_argument("--config"); s.add_argument("--pages")
    s = sub.add_parser("render", help="rebuild PDF with Arabic")
    s.add_argument("pdf"); s.add_argument("out"); s.add_argument("--tr", nargs="*", default=[])
    s.add_argument("--config"); s.add_argument("--pages"); s.add_argument("--debug", action="store_true")
    s.add_argument("--report", help="write issues JSON here")
    s = sub.add_parser("preview", help="PNG previews")
    s.add_argument("pdf"); s.add_argument("out_dir"); s.add_argument("--pages"); s.add_argument("--dpi", type=int, default=95)
    s.add_argument("--mode", choices=["pages", "pairs", "grid"], default="pages"); s.add_argument("--compare")
    s.add_argument("--cols", type=int, default=3)
    s = sub.add_parser("overlay", help="write Arabic boxes from a JSON spec (flattened pages)")
    s.add_argument("pdf"); s.add_argument("spec"); s.add_argument("out"); s.add_argument("--debug", action="store_true")
    s = sub.add_parser("text", help="extract text, repairing Arabic")
    s.add_argument("pdf"); s.add_argument("--pages"); s.add_argument("--raw", action="store_true")
    s.add_argument("--reverse", action="store_true", help="undo visual-order (reversed) Arabic lines")
    s = sub.add_parser("polish", help="show polish() on a string")
    s.add_argument("text"); s.add_argument("--digits", default="western")
    a = ap.parse_args(argv)

    if a.cmd == "fonts":
        print("fonts ready in", ensure_fonts(a.fonts))
        if a.check:
            for fam, w, ok in check_fonts(a.fonts):
                print(f"  {fam:8} {w}  {'searchable' if ok else 'NOT searchable (looks right, copies as garbage)'}")
    elif a.cmd == "inspect":
        rep = inspect_pdf(a.pdf, load_config(a.config))
        if a.json: print(json.dumps(rep, ensure_ascii=False, indent=1)); return
        print(f"{'page':>4} {'kind':10} {'chars':>6} {'img%':>5} {'ar':>4}")
        for p in rep["pages"]:
            print(f"{p['page']:>4} {p['kind']:10} {p['chars']:>6} {int(p['image_cover'] * 100):>4}% {p['arabic_spans']:>4}")
        print("\nfonts (role = current guess; override with font_rules):")
        for f in rep["fonts"]:
            print(f"  {f['font'][:34]:34} {f['guessed_role']:8} n={f['spans']:<5} sizes={f['sizes']} {f['colors'][:2]} {f['samples'][:2]}")
        if rep["config_skeleton"]["font_rules"]:
            print("\nType3 fonts have no names; assign roles in a config, e.g.:")
            print(json.dumps(rep["config_skeleton"], indent=1)[:2000])
    elif a.cmd == "extract":
        res = extract(a.pdf, load_config(a.config), load_translations(a.tr), a.pages)
        n = sum(len(v) for v in res.values())
        txt = json.dumps(res, ensure_ascii=False, indent=1)
        if a.out: open(a.out, "w", encoding="utf-8").write(txt)
        else: print(txt)
        print(f"{n} untranslated keys on {len(res)} pages" + (f" -> {a.out}" if a.out else ""), file=sys.stderr)
    elif a.cmd == "render":
        iss = render(a.pdf, a.out, load_translations(a.tr), load_config(a.config), a.pages, a.fonts, a.debug)
        if a.report: json.dump(iss, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        cnt = {}
        for i in iss: cnt[i["type"]] = cnt.get(i["type"], 0) + 1
        for i in sorted(iss, key=lambda i: (i["type"] != "missing", i.get("scale", 1), i["page"]))[:25]:
            print(f"  p{i['page']:<3} {i['type']:11} {i.get('scale', ''):<5} {i['key'][:70]}")
        print("wrote", a.out, cnt or "no issues")
    elif a.cmd == "preview":
        for f in preview(a.pdf, a.out_dir, a.pages, a.dpi, a.mode, a.compare, a.cols): print(f)
    elif a.cmd == "overlay":
        iss = overlay(a.pdf, json.load(open(a.spec, encoding="utf-8")), a.out, a.fonts, a.debug)
        for i in iss: print("  tight:", i)
        print("wrote", a.out)
    elif a.cmd == "text":
        print(dump_text(a.pdf, a.pages, fix=not a.raw, reverse=a.reverse))
    elif a.cmd == "polish":
        r = polish(a.text, digits=a.digits)
        print(r); print(" ".join(f"U+{ord(c):04X}" for c in r if ord(c) in (0xA0, 0x2060, 0x202A, 0x202C)))


if __name__ == "__main__":
    main()
