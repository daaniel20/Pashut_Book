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
5. Decide how to cut each photo to fit its spot, keeping every face in and
   keeping more of the top (raised hands, heads) than the bottom. If that's
   not possible, or it would cut off too much, the WHOLE photo is shown,
   a bit smaller, instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import permutations

import designs

# The most of a photo we cut off to fill a spot. Photos with people are barely
# cut (a rule from the Rega album maker, see docs/research-notes.md), photos
# without people (landscapes, food) may be cut more: 0.26 lets an upright
# phone photo (3:4) fill a square spot.
MAX_CUT = 0.26
MAX_CUT_PEOPLE = 0.22
# How much the layout choice cares about filling the page with photo rather
# than background (owner's feedback: photos looked small on the page).
FILL_WEIGHT = 1.0
# No photo is shown smaller than this on its short side (mm), unless a page
# has no other way to fit its photos.
MIN_PHOTO_MM = 45
# Room kept around faces, in face sizes: above (hair, raised hands), below
# (chin, shoulders) and at the sides.
ROOM_ABOVE, ROOM_BELOW, ROOM_SIDE = 1.0, 0.6, 0.5
# Where to cut when there are no faces, or room to spare: 0 = keep the top,
# 0.5 = the middle. A little toward the top keeps heads and raised hands.
KEEP_TOP = 0.3


@dataclass
class Spot:
    photo: str          # the photo's name
    x: float            # mm from the page's left edge
    y: float            # mm from the page's top edge
    width: float
    height: float
    small: bool         # a small spot (lower-quality photos may go here)
    # The part of the photo shown: (x, y, width, height), as parts of the photo
    # (0 to 1). (0, 0, 1, 1) = the whole photo.
    crop: tuple = (0, 0, 1, 1)


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
        allow_full = style["full_page"] and "full" not in recent[-3:]
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
            if any(photo.grade != "ok" and not shape[1]
                   for photo, shape in zip(order, shapes)):
                continue    # a lower-quality photo in a big spot: not allowed
            cuts = [_cut(photo, shape[0], full_page=name == "full")
                    for photo, shape in zip(order, shapes)]
            if name == "full" and None in cuts:
                continue    # an edge-to-edge page must be cut to fit
            # Cutting costs what is cut off. Showing the whole photo smaller costs
            # twice the empty space around it, plus extra (an uneven page looks
            # less tidy), so a photo is shrunk only a little, never to a tiny size.
            cost = 0
            covered = 0     # mm² of the page covered by photos
            for photo, (aspect, _, width, height), cut in zip(order, shapes, cuts):
                loss = _crop_loss(photo, aspect)
                if cut is None:
                    cost += 2 * loss + 0.2
                    width, height = _whole_size(photo, width, height)
                else:
                    cost += loss
                if min(width, height) < MIN_PHOTO_MM:
                    cost += 2       # too small to enjoy: only if nothing else fits
                covered += width * height
            score = cost / len(group)
            # Bigger photos, less empty background.
            score += FILL_WEIGHT * (1 - covered / (designs.PAGE_WIDTH * designs.PAGE_HEIGHT))
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
    """(width / height, is it small?, width, height) for each spot of a template,
    on the real page (mm)."""
    page = _page(name, [None] * len(designs.TEMPLATES[name]), "", style)
    return [(s.width / s.height, s.small, s.width, s.height) for s in page.spots]


def _whole_size(photo, width, height):
    """The size of the whole photo when it is fitted inside a spot."""
    if not photo.width or not photo.height:
        return width, height
    aspect = photo.width / photo.height
    return (width, width / aspect) if width / height < aspect else (height * aspect, height)


def _crop_loss(photo, spot_aspect):
    """How much of the photo is cut off to fill the spot (0 = nothing)."""
    if not photo.width or not photo.height:
        return 0.5
    aspect = photo.width / photo.height
    return 1 - min(aspect, spot_aspect) / max(aspect, spot_aspect)


# ---------- cutting a photo to fit its spot ----------

def _cut(photo, spot_aspect, full_page=False):
    """The part of the photo to show in a spot of this shape: (x, y, w, h) as
    parts of the photo. None if it can't be cut without losing a face or too
    much of the photo: then the whole photo is shown, smaller."""
    if not photo.width or not photo.height:
        return (0, 0, 1, 1)
    aspect = photo.width / photo.height
    faces = _faces_box(getattr(photo, "faces", None) or [])
    # A photo with people is trimmed less, except on an edge-to-edge page, which
    # must be filled (an upright phone photo on a square page loses 25%).
    limit = MAX_CUT_PEOPLE if faces and not full_page else MAX_CUT
    if _crop_loss(photo, spot_aspect) > limit:
        return None
    if aspect > spot_aspect:            # wider than the spot: cut the sides
        width = spot_aspect / aspect
        x = _place(width, faces and (faces[0], faces[2]), 0.5)
        return None if x is None else (round(x, 4), 0, round(width, 4), 1)
    height = aspect / spot_aspect       # taller than the spot: cut top and bottom
    y = _place(height, faces and (faces[1], faces[3]), KEEP_TOP)
    return None if y is None else (0, round(y, 4), 1, round(height, 4))


def _faces_box(faces):
    """One box around all the faces, with room around them: (left, top, right, bottom)."""
    if not faces:
        return None
    left = min(x - ROOM_SIDE * w for x, y, w, h in faces)
    right = max(x + w + ROOM_SIDE * w for x, y, w, h in faces)
    top = min(y - ROOM_ABOVE * h for x, y, w, h in faces)
    bottom = max(y + h + ROOM_BELOW * h for x, y, w, h in faces)
    return (max(0, left), max(0, top), min(1, right), min(1, bottom))


def _place(size, keep, where):
    """Where a window of this size (0-1) starts, so it holds the part to keep
    (start, end). None if that part doesn't fit."""
    if not keep:
        return (1 - size) * where
    lowest = max(0, keep[1] - size)     # the window must reach the end of the faces
    highest = min(1 - size, keep[0])    # and start before them
    if lowest > highest + 1e-6:
        return None
    return lowest + (highest - lowest) * where


def _fit_inside(spot, photo):
    """Make the spot the photo's own shape, in the middle of where it was."""
    aspect = photo.width / photo.height
    if spot.width / spot.height > aspect:
        width = spot.height * aspect
        spot.x, spot.width = round(spot.x + (spot.width - width) / 2, 2), round(width, 2)
    else:
        height = spot.width / aspect
        spot.y, spot.height = round(spot.y + (spot.height - height) / 2, 2), round(height, 2)


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
        if photo is not None:
            _fit_photo(page.spots[-1], photo, full_page=name == "full")
    return page


def _fit_photo(spot, photo, full_page=False):
    cut = _cut(photo, spot.width / spot.height, full_page)
    if cut is None:
        _fit_inside(spot, photo)
    else:
        spot.crop = cut


def _cover(usable, style, title):
    """The front cover: an early good photo that fits the space well, with room
    for the title below it."""
    margin = style["margin"] * 1.5
    text_height = designs.PAGE_HEIGHT * 0.2 if title else 0
    width = designs.PAGE_WIDTH - 2 * margin
    height = designs.PAGE_HEIGHT - 2 * margin - text_height
    good = [p for p in usable if p.grade == "ok"][:10] or usable[:1]
    photo = next((p for p in good if _cut(p, width / height)), good[0])
    cover = Page("cover", style["cover_background"])
    cover.spots.append(Spot(photo=photo.name, x=margin, y=margin,
                            width=width, height=height, small=False))
    _fit_photo(cover.spots[0], photo)
    return cover
