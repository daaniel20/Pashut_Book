"""Automatic album layout (task 2.2): which photos go on which page, and where.

Input: the photos in album order, each with its size and quality grade
(from quality.py). Output: an Album, a plan of every page in millimetres.
It doesn't draw anything (render.py does that), and it doesn't need Pillow,
so the same plan can later be drawn as preview images (2.4) or a print PDF (2.3).

How it decides, in short:
1. Leave out the "skip" photos (blurry, duplicates, too small).
2. Decide how many pages (the printer's minimum, about 2-3 photos a page).
3. Split the photos, in order, into page groups of 1-4 photos, with some
   variety (a few single-photo pages between busier ones).
4. For each group, pick the template (designs.TEMPLATES) that crops the
   photos the least, with the rule: lower-quality photos only in small spots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import permutations

import designs


@dataclass
class Spot:
    photo: str          # the photo's name
    x: float            # mm from the page's left edge
    y: float            # mm from the page's top edge
    width: float
    height: float
    small: bool         # a small spot (lower-quality photos may go here)


@dataclass
class Page:
    template: str
    background: str
    spots: list = field(default_factory=list)


@dataclass
class Album:
    design: str
    title: str | None
    width: float
    height: float
    cover: Page
    pages: list = field(default_factory=list)
    left_out: list = field(default_factory=list)   # names of photos not used
    notes: list = field(default_factory=list)      # things the owner should know

    def to_dict(self):
        """A plain version, to save as layout.json (no photos inside, only names)."""
        def page(p):
            return {"template": p.template, "background": p.background,
                    "spots": [vars(s) for s in p.spots]}
        return {"design": self.design, "title": self.title,
                "page_size_mm": [self.width, self.height],
                "cover": page(self.cover), "pages": [page(p) for p in self.pages],
                "left_out": self.left_out, "notes": self.notes}


def make_album(photos, design, title=None):
    """photos: PhotoCheck results from quality.check_all(), in album order
    (anything with .name, .width, .height and .grade works)."""
    if design not in designs.DESIGNS:
        raise ValueError(f"Unknown design: {design}")
    style = designs.DESIGNS[design]
    usable = [p for p in photos if p.grade != "skip"]
    album = Album(design=design, title=title, width=designs.PAGE_WIDTH,
                  height=designs.PAGE_HEIGHT, cover=None,
                  left_out=[p.name for p in photos if p.grade == "skip"])
    if not usable:
        raise ValueError("No usable photos")

    album.cover = _cover(usable, style, title)
    sizes = page_sizes(len(usable))
    recent = []   # templates of the last pages, for variety
    start = 0
    for number, size in enumerate(sizes):
        group = usable[start:start + size]
        start += size
        allow_full = style["full_page"] and "full" not in recent[-5:]
        name, order = _best_template(group, recent, allow_full, style)
        recent.append(name)
        background = style["backgrounds"][number % len(style["backgrounds"])]
        album.pages.append(_page(name, order, background, style))

    # Printers need an even number of pages: add an empty page at the end.
    while len(album.pages) % designs.PAGE_MULTIPLE:
        album.pages.append(Page("empty", style["backgrounds"][0]))
    if len(album.pages) < designs.MIN_PAGES:
        album.notes.append(f"Only {len(usable)} usable photos: the album has "
                           f"{len(album.pages)} pages, fewer than the minimum "
                           f"({designs.MIN_PAGES}).")
    return album


def page_sizes(count):
    """How many photos go on each page, in order. Adds up to count."""
    pages = math.ceil(count / designs.PHOTOS_PER_PAGE)
    pages = max(designs.MIN_PAGES, min(designs.MAX_PAGES, pages))
    pages = max(math.ceil(count / 4), min(pages, count))   # 1-4 photos a page
    pages = min(pages, count)
    # Spread the photos evenly first (e.g. 2, 3, 2, 3 …)
    sizes = [(i + 1) * count // pages - i * count // pages for i in range(pages)]
    # Then add variety: in every third pair of pages, move a photo from one
    # page to the other (2+3 becomes 1+4: one big photo next to a busy page).
    for pair in range(1, pages // 2, 3):
        a, b = sorted((2 * pair, 2 * pair + 1), key=lambda i: sizes[i])
        if sizes[a] > 1 and sizes[b] < 4:
            sizes[a] -= 1
            sizes[b] += 1
    return sizes


# ---------- choosing a template for one page ----------

def _best_template(group, recent, allow_full, style):
    """Returns (template name, photos in spot order)."""
    best = None
    for name, spots in designs.TEMPLATES.items():
        if len(spots) != len(group) or (name == "full" and not allow_full):
            continue
        shapes = _spot_shapes(name, style)
        for order in _orders(group):
            if any(photo.grade != "ok" and not small
                   for photo, (_, small) in zip(order, shapes)):
                continue    # a lower-quality photo in a big spot: not allowed
            crop = sum(_crop_loss(p, aspect) for p, (aspect, _) in zip(order, shapes))
            score = crop / len(group)
            score += 0.05 * _out_of_order(group, order)   # keep the order when we can
            if name in recent[-2:]:
                score += 0.15      # don't repeat the same look page after page
            if name.endswith("_small"):
                score += 1         # small photos only when we must
            if name == "full":
                score -= 0.1       # a full-page photo now and then looks great
            if best is None or score < best[0]:
                best = (score, name, order)
    return best[1], best[2]


def _orders(group):
    """Every way to place the photos in the spots (at most 4 photos = 24 ways),
    so portrait photos can go in tall spots and landscape photos in wide ones."""
    return permutations(group)


def _out_of_order(group, order):
    """How many pairs of photos swapped places (spots are in reading order)."""
    position = {id(photo): i for i, photo in enumerate(group)}
    places = [position[id(photo)] for photo in order]
    return sum(a > b for i, a in enumerate(places) for b in places[i + 1:])


def _spot_shapes(name, style):
    """(width / height, is it small?) for each spot of a template, on the real page."""
    page = _page(name, [None] * len(designs.TEMPLATES[name]), "", style)
    return [(s.width / s.height, s.small) for s in page.spots]


def _crop_loss(photo, spot_aspect):
    """How much of the photo is cut off to fill the spot (0 = nothing)."""
    if not photo.width or not photo.height:
        return 0.5
    aspect = photo.width / photo.height
    return 1 - min(aspect, spot_aspect) / max(aspect, spot_aspect)


# ---------- turning a template into spots in mm ----------

def _page(name, photos, background, style):
    page = Page(name, background)
    if name == "full":
        margin, gap = 0, 0
    else:
        margin, gap = style["margin"], style["gap"]
    inner_w = designs.PAGE_WIDTH - 2 * margin
    inner_h = designs.PAGE_HEIGHT - 2 * margin
    longest_page_side = max(designs.PAGE_WIDTH, designs.PAGE_HEIGHT)
    for photo, (x, y, w, h) in zip(photos, designs.TEMPLATES[name]):
        if designs.RIGHT_TO_LEFT:
            x = 1 - x - w
        # Take half the gap off each side that touches another photo.
        left = gap / 2 if x > 0 else 0
        right = gap / 2 if x + w < 1 else 0
        top = gap / 2 if y > 0 else 0
        bottom = gap / 2 if y + h < 1 else 0
        spot_w = w * inner_w - left - right
        spot_h = h * inner_h - top - bottom
        page.spots.append(Spot(
            photo=getattr(photo, "name", None),
            x=round(margin + x * inner_w + left, 2),
            y=round(margin + y * inner_h + top, 2),
            width=round(spot_w, 2), height=round(spot_h, 2),
            small=max(spot_w, spot_h) <= designs.SMALL_SPOT * longest_page_side,
        ))
    return page


def _cover(usable, style, title):
    """The front cover: the first good photo, with room for the title below it."""
    photo = next((p for p in usable if p.grade == "ok"), usable[0])
    margin = style["margin"] * 1.5
    text_height = designs.PAGE_HEIGHT * 0.2 if title else 0
    cover = Page("cover", style["cover_background"])
    cover.spots.append(Spot(photo=photo.name, x=margin, y=margin,
                            width=designs.PAGE_WIDTH - 2 * margin,
                            height=designs.PAGE_HEIGHT - 2 * margin - text_height,
                            small=False))
    return cover
