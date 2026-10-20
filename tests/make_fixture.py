"""Build tests/fixture/en.pdf: a small invented English document with the layout
features arpdf has to handle (header band, serif title, cards with accent bars,
bullets, a chip, a table, numbered step badges, a footer badge).
Run: python3 tests/make_fixture.py"""
import os
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixture", "en.pdf")

INK, MUTED, ACCENT, CARD, DARK, WHITE = (0.17, 0.11, 0.2), (0.46, 0.4, 0.48), (0.78, 0.33, 0.17), (1, 1, 1), (0.17, 0.11, 0.2), (1, 1, 1)
BG = (1, 0.98, 0.95)


def chrome(page, n):
    page.draw_rect(page.rect, color=None, fill=BG)
    page.insert_text((37, 25), "GREENLEAF KITCHEN · WEEKLY PLAN", fontname="hebo", fontsize=8, color=MUTED)
    page.draw_line((37, 40), (558, 40), color=(0.9, 0.86, 0.8), width=0.6)
    page.insert_text((37, 828), "Prepared by the Greenleaf team", fontname="helv", fontsize=9, color=MUTED)
    page.draw_circle((546, 824), 11, color=None, fill=DARK)
    page.insert_text((543, 828), str(n), fontname="hebo", fontsize=9, color=WHITE)


def card(page, y0, y1, accent, title, body_lines):
    page.draw_rect(pymupdf.Rect(37, y0, 558, y1), color=None, fill=CARD, radius=0.06)
    page.draw_rect(pymupdf.Rect(37, y0, 41, y1), color=None, fill=accent)
    page.insert_text((56, y0 + 22), title, fontname="hebo", fontsize=12, color=accent)
    for k, ln in enumerate(body_lines):
        page.insert_text((56, y0 + 40 + k * 15), ln, fontname="helv", fontsize=10, color=INK)


doc = pymupdf.open()
p = doc.new_page(width=595, height=842)
chrome(p, 1)
p.insert_text((37, 66), "WELCOME", fontname="tibo", fontsize=11, color=ACCENT)
p.insert_text((37, 96), "Your week of simple meals", fontname="tibo", fontsize=24, color=INK)
for k, ln in enumerate(["This plan gives you two calm meals a day and one snack. Every recipe uses",
                        "ingredients from a normal supermarket, and each card lists exact amounts",
                        "so you can shop once and cook twice."]):
    p.insert_text((37, 122 + k * 17), ln, fontname="helv", fontsize=11, color=MUTED)
card(p, 180, 250, (0.31, 0.54, 0.33), "How to use the cards",
     ["Pick one breakfast and one lunch. Weigh rice and pasta after cooking,",
      "and oats before cooking. Swap any vegetable for another one you like."])
card(p, 262, 332, (0.85, 0.51, 0.17), "Drink about 2 liters",
     ["Water, plain tea or coffee without sugar. Add a glass for every hour",
      "of exercise."])
# bullets with drawn dots
p.insert_text((56, 362), "Shopping basics", fontname="hebo", fontsize=12, color=INK)
for k, ln in enumerate(["Eggs, yogurt and white cheese", "Rice, oats and whole-wheat bread",
                        "Tomatoes, cucumbers and lemons"]):
    p.draw_circle((60, 381 + k * 18), 2.2, color=None, fill=ACCENT)
    p.insert_text((70, 385 + k * 18), ln, fontname="helv", fontsize=10, color=INK)
# chip
p.draw_rect(pymupdf.Rect(470, 352, 540, 366), color=None, fill=ACCENT, radius=0.4)
p.insert_text((482, 362), "Easy week", fontname="hebo", fontsize=7.5, color=WHITE)

p = doc.new_page(width=595, height=842)
chrome(p, 2)
p.insert_text((37, 66), "PORTIONS", fontname="tibo", fontsize=11, color=ACCENT)
p.insert_text((37, 96), "How much to eat", fontname="tibo", fontsize=24, color=INK)
cols = [45, 200, 330]
p.draw_rect(pymupdf.Rect(37, 112, 558, 134), color=None, fill=DARK, radius=0.2)
for x, h in zip(cols, ["Food", "Amount", "Tip"]):
    p.insert_text((x, 127), h, fontname="hebo", fontsize=9.5, color=WHITE)
rows = [("Cooked rice", "250 g", "Weigh it on the plate"), ("Rolled oats", "80 g", "Weigh them dry"),
        ("Chicken breast", "about 39 g protein", "Cooked weight is a quarter less")]
for k, row in enumerate(rows):
    y = 140 + k * 30
    p.draw_rect(pymupdf.Rect(37, y, 558, y + 26), color=(0.9, 0.86, 0.8), fill=CARD, width=0.6, radius=0.2)
    for x, cell, f in zip(cols, row, ["hebo", "helv", "helv"]):
        p.insert_text((x, y + 17), cell, fontname=f, fontsize=9.5, color=INK)
# numbered steps with badges on the left
p.insert_text((37, 262), "Cook the rice", fontname="tibo", fontsize=15, color=INK)
for k, ln in enumerate(["Rinse the rice until the water runs clear.",
                        "Simmer it covered for 12 minutes.",
                        "Rest it for 5 minutes, then fluff with a fork."]):
    y = 288 + k * 22
    p.draw_circle((46, y - 3.5), 6, color=None, fill=ACCENT)
    p.insert_text((43.5, y), str(k + 1), fontname="hebo", fontsize=7, color=WHITE)
    p.insert_text((60, y), ln, fontname="helv", fontsize=10, color=INK)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc.save(OUT)
print("wrote", OUT)
