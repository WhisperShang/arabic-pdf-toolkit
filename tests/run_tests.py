#!/usr/bin/env python3
"""Regression tests for arpdf.

  python3 tests/run_tests.py                  # run everything
  python3 tests/run_tests.py --update-golden  # accept current output as the new reference

Layers:
  1. unit     – Arabic text helpers (polish, digits, quantities, normalisation)
  2. fonts    – every family that claims to be searchable extracts back as correct text
  3. fixture  – renders tests/fixture/en.pdf (invented, safe to commit) and compares each page
                with tests/golden/fixture_pN.png
  4. private  – every folder in tests/private/<name>/ with in.pdf, tr/, optional config.json and
                golden.pdf is rendered and compared page by page with golden.pdf. tests/private is
                git-ignored: real client documents stay on your machine.
"""
import glob, json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import arpdf as A  # noqa: E402
import pymupdf  # noqa: E402

THRESHOLD = 0.3  # % of pixels allowed to differ (anti-aliasing noise is ~0.1%)
DPI = 60
FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok: FAILS.append(name)


def diff_pct(pa, pb):
    if (pa.width, pa.height) != (pb.width, pb.height): return 100.0
    sa, sb = pa.samples, pb.samples
    n = sum(1 for q in range(0, len(sa), 3) if abs(sa[q] - sb[q]) + abs(sa[q + 1] - sb[q + 1]) + abs(sa[q + 2] - sb[q + 2]) > 60)
    return 100 * n / (pa.width * pa.height)


def unit():
    print("unit")
    p = A.polish("حوالي 1½ كوباية و250 جم و60–70 جم ≈ 39 جم")
    check("polish glues number+unit", "250" + A.NBSP + "جم" in p)
    check("polish joins ranges", "60" + A.WJ + "–" + A.WJ + "70" in p)
    check("polish glues ≈", "≈" + A.NBSP + "39" in p)
    check("polish isolates fractions", A.LRE + "1½" + A.PDF_ in p)
    check("polish replace", A.polish("1 معلقة صغيرة", {"معلقة صغيرة": "م.ص"}) == "1" + A.NBSP + "م.ص")
    check("arabic digits", A.to_arabic_digits("12.5 و 1,708") == "١٢٫٥ و ١٬٧٠٨")
    check("western digits", A.to_western_digits("١٢٫٥ ۳") == "12.5 3")
    check("auto_quantity", A.auto_quantity("≈ 39 g") == "≈ 39 جم" and A.auto_quantity("1,708 kcal") == "1,708 سعر")
    check("auto_quantity rejects prose", A.auto_quantity("Weigh it") is None)
    check("normalize_arabic", A.normalize_arabic("أَحْمَد") == "احمد")
    check("presentation forms", A.fix_presentation_forms("ﺍﻟﻌﺮﺑﻴﺔ") == "العربية")
    check("has_arabic", A.has_arabic("سلام") and not A.has_arabic("hello"))
    check("is_emoji", A.is_emoji("💡") and not A.is_emoji("♥"))
    check("source is escape-free", "\\" + "u" not in open(os.path.join(ROOT, "arpdf.py"), encoding="utf-8").read())


def fonts():
    print("fonts")
    for fam, w, ok in A.check_fonts():
        if A.FAMILIES[fam]["searchable"]:
            check(f"{fam} {w} searchable", ok)


def compare_pdf(out_pdf, golden_pngs, update, label):
    doc = pymupdf.open(out_pdf)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=DPI, alpha=False)
        g = golden_pngs(i)
        if update or not os.path.exists(g):
            os.makedirs(os.path.dirname(g), exist_ok=True); pix.save(g)
            print(f"  wrote golden {os.path.relpath(g, ROOT)}")
            continue
        d = diff_pct(pix, pymupdf.Pixmap(g))
        check(f"{label} page {i + 1} matches golden", d <= THRESHOLD, f"{d:.2f}% differ")


def fixture(update):
    print("fixture")
    src = os.path.join(HERE, "fixture", "en.pdf")
    tr = A.load_translations([os.path.join(HERE, "fixture", "tr")])
    cfg = A.load_config(os.path.join(HERE, "fixture", "config.json") if os.path.exists(os.path.join(HERE, "fixture", "config.json")) else None)
    left = A.extract(src, cfg, tr, None)
    check("every fixture key translated", not left, json.dumps(left, ensure_ascii=False)[:200])
    out = os.path.join(tempfile.mkdtemp(), "fixture_ar.pdf")
    issues = A.render(src, out, tr, cfg)
    check("render reports no issues", not issues, str(issues[:3]))
    text = A.dump_text(out)
    check("output Arabic is searchable", "أسبوعك بوجبات بسيطة" in text and "اطبخ الرز" in text)
    compare_pdf(out, lambda i: os.path.join(HERE, "golden", f"fixture_p{i + 1}.png"), update, "fixture")


def private(update):
    suites = sorted(d for d in glob.glob(os.path.join(HERE, "private", "*")) if os.path.isdir(d))
    if not suites: return
    print("private")
    for d in suites:
        name = os.path.basename(d)
        src = os.path.join(d, "in.pdf")
        if not os.path.exists(src): continue
        cfgp = os.path.join(d, "config.json")
        cfg = A.load_config(cfgp if os.path.exists(cfgp) else None)
        tr = A.load_translations([os.path.join(d, "tr")])
        out = os.path.join(tempfile.mkdtemp(), f"{name}.pdf")
        t = time.time()
        issues = A.render(src, out, tr, cfg)
        check(f"{name}: no missing keys", not [i for i in issues if i["type"] == "missing"])
        golden = os.path.join(d, "golden.pdf")
        if update or not os.path.exists(golden):
            import shutil; shutil.copy(out, golden); print(f"  wrote golden {name}/golden.pdf"); continue
        gd, od = pymupdf.open(golden), pymupdf.open(out)
        check(f"{name}: same page count", len(gd) == len(od))
        worst = max((diff_pct(od[i].get_pixmap(dpi=DPI, alpha=False), gd[i].get_pixmap(dpi=DPI, alpha=False)), i + 1)
                    for i in range(min(len(gd), len(od))))
        check(f"{name}: all pages match golden ({time.time() - t:.0f}s)", worst[0] <= THRESHOLD,
              f"worst page {worst[1]}: {worst[0]:.2f}% differ")


if __name__ == "__main__":
    update = "--update-golden" in sys.argv
    A.ensure_fonts(quiet=True)
    unit(); fonts(); fixture(update); private(update)
    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all tests passed'}")
    sys.exit(1 if FAILS else 0)
