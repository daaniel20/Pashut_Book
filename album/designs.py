"""The album's page size and the 2 designs (task 2.2).

Everything about how the album LOOKS is here, as settings, so it's easy to
change after the printer is chosen (task S.2) and the 2 templates are ready
(task S.3). Sizes are in millimetres (mm), like a printer's specifications.

⚠️ The page size below is a placeholder (a common 20x20 cm square album)
until the printer's real specifications arrive. Change PAGE_WIDTH and
PAGE_HEIGHT, and the whole album adapts.
"""

from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# ---------- the book ----------
PAGE_WIDTH = 200    # mm (placeholder until S.2)
PAGE_HEIGHT = 200   # mm
MIN_PAGES = 20      # inside pages, without the cover (placeholder until S.2)
MAX_PAGES = 40
PAGE_MULTIPLE = 2   # printers need an even number of pages (some need 4)
PHOTOS_PER_PAGE = 2.5   # on average, when there are enough photos
# About this part of the pages has one photo from edge to edge (no background).
# Owner's choice: started with 20%; raised to 30% on Nov 24, 2026 (not enough
# of them in the owner's test album). Above ~35% the other pages get crowded.
EDGE_TO_EDGE_SHARE = 0.3

# A photo spot is "small" when its longest side is at most this part of the
# page. Lower-quality photos (grade "small" in quality.py) go only there.
SMALL_SPOT = 0.65

# Hebrew books open from the right: the first photo of a page goes on the right.
RIGHT_TO_LEFT = True


# ---------- the 2 designs ----------
# margin: empty space around the photos (mm). gap: space between photos (mm).
# corner: rounded photo corners (mm, 0 = square). border: white frame (mm).
# backgrounds: page colours, used in turn. full_page: allow photos that cover
# a whole page edge to edge (only with "ok" photos).
DESIGNS = {
    "classic": {
        "backgrounds": ["#FFFFFF"],
        "margin": 9,
        "gap": 4,
        "corner": 0,
        "border": 0,
        "full_page": True,
        "font": FONTS_DIR / "FrankRuhlLibre.ttf",
        "font_weight": "Medium",
        "title_color": "#2B2B2B",
        "cover_background": "#FFFFFF",
    },
    "colorful": {
        "backgrounds": ["#FDE2E4", "#E2F0CB", "#CDE7F0", "#FFF1C1", "#E8DFF5"],
        "margin": 10,
        "gap": 5,
        "corner": 4,
        "border": 2,
        "full_page": True,
        "font": FONTS_DIR / "Rubik.ttf",
        "font_weight": "SemiBold",
        "title_color": "#3A3A3A",
        "cover_background": "#FFF1C1",
    },
}


# ---------- page templates ----------
# Each template is a list of photo spots: (x, y, width, height), as parts of the
# space inside the margins (0 = left/top edge, 1 = right/bottom edge).
# Written left to right; mirrored for Hebrew (RIGHT_TO_LEFT).
# The gap between photos is taken off later, so spots here may touch.
TEMPLATES = {
    # 1 photo
    "full":       [(0, 0, 1, 1)],          # edge to edge, no margin (see layout.py)
    "one":        [(0, 0, 1, 1)],
    "one_small":  [(0.2, 0.15, 0.6, 0.7)],
    # 2 photos
    "two_side":   [(0, 0.18, 0.5, 0.64), (0.5, 0.18, 0.5, 0.64)],   # 2 upright (3:4), uncut
    "two_side_tall": [(0, 0.06, 0.5, 0.88), (0.5, 0.06, 0.5, 0.88)],  # 2 upright, trimmed a little
    "two_tall":   [(0, 0, 0.5, 1), (0.5, 0, 0.5, 1)],               # 2 tall (phone screen, 9:16)
    "two_stack":  [(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)],
    "two_offset": [(0, 0, 0.7, 0.5), (0.3, 0.5, 0.7, 0.5)],     # 2 wide photos
    "two_mixed":  [(0, 0.1, 0.5, 0.8), (0.5, 0.28, 0.5, 0.44)],  # 1 upright + 1 wide
    # 3 photos
    "three_side": [(0, 0, 0.6, 1), (0.6, 0, 0.4, 0.5), (0.6, 0.5, 0.4, 0.5)],
    "three_top":  [(0, 0, 1, 0.6), (0, 0.6, 0.5, 0.4), (0.5, 0.6, 0.5, 0.4)],
    "three_tall": [(0, 0.2, 1 / 3, 0.6), (1 / 3, 0.2, 1 / 3, 0.6), (2 / 3, 0.2, 1 / 3, 0.6)],
    "three_small": [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5), (0.25, 0.5, 0.5, 0.5)],
    # 4 photos
    "four":       [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5), (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)],
}
