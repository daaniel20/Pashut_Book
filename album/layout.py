"""Automatic album layout (task 2.2): which photos go on which page, and where.

Input: the photos in album order, each with its size and quality grade
(from quality.py). Output: an Album, a plan of every page in millimetres.
It doesn't draw anything (render.py does that), and it doesn't need Pillow,
so the same plan can later be drawn as preview images (2.4) or a print PDF (2.3).

How it decides, in short:
1. Leave out the "skip" photos (blurry, duplicates, too small).
2. Decide how many pages: about 2.5 photos a page, within the printer's
   minimum and maximum.
3. Split the photos, in order, into pages of 1-4 photos, looking at their
   shapes: photos that fit together share a page (mixed shapes get 3-4 photos
   so the page isn't empty), other photos get a page of their own.
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
# The cover is always edge to edge when it can be: a wide photo may lose up to
# half (its sides) on the square cover, as long as every face stays in.
# (Owner's test: a wide selfie fell back to a small photo with white around it.)
MAX_CUT_COVER = 0.5
# How much the layout choice cares about filling the page with photo rather
# than background (owner's feedback: photos looked small on the page).
FILL_WEIGHT = 1.0
# Layouts that adapt to the photos' shapes, so every photo fills its spot
# exactly (no cutting, no white gaps around a photo). Owner's feedback: a small
# photo in a fixed spot of the wrong shape left white gaps (pages 1 and 5).
#   flex_row2: 2 side by side   flex_col2: 2 stacked
#   flex_side3: 1 big + 2 stacked beside it   flex_top3: 1 big + 2 below it
#   flex_grid4: 2 rows of 2
FLEX = {"flex_row2": 2, "flex_col2": 2, "flex_side3": 3, "flex_top3": 3, "flex_grid4": 4}
# Planning pages: the cost of giving 2 neighbouring pages the same number of photos.
REPEAT_COST = 0.15
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
    # Where the cover title goes: "bottom" or "top" (a band over the
    # edge-to-edge photo, never over a face), or "below" (under a smaller photo).
    title_place: str = "below"
    pages: list = field(default_factory=list)
    left_out: list = field(default_factory=list)   # names of photos not used
    notes: list = field(default_factory=list)      # things the owner should know

    def to_dict(self):
        """A plain version, to save as layout.json (no photos inside, only names)."""
        def page(p):
            return {"template": p.template, "background": p.background,
                    "spots": [vars(s) for s in p.spots]}
        return {"design": self.design, "title": self.title,
                "page_size_mm": [self.width, self.height], "title_place": self.title_place,
                "cover": page(self.cover), "pages": [page(p) for p in self.pages],
                "left_out": self.left_out, "notes": self.notes}


def make_album(photos, design, title=None, cover=None):
    """photos: PhotoCheck results from quality.check_all(), in album order
    (anything with .name, .width, .height and .grade works).
    cover: the name of the photo the customer chose for the cover, if any."""
    if design not in designs.DESIGNS:
        raise ValueError(f"Unknown design: {design}")
    style = designs.DESIGNS[design]
    usable = [p for p in photos if p.grade != "skip"]
    album = Album(design=design, title=title, width=designs.PAGE_WIDTH,
                  height=designs.PAGE_HEIGHT, cover=None,
                  left_out=[p.name for p in photos if p.grade == "skip"])
    if not usable:
        raise ValueError("No usable photos")

    chosen = _cover_choice(photos, cover)
    if cover and chosen is None:
        album.notes.append(f"The customer's cover photo ({cover}) can't be used "
                           "(blurry or too small): another photo was chosen.")
    album.cover, album.title_place = _cover(usable, style, title, chosen)
    full = pick_full_pages(usable, style, album.cover.spots[0].photo)
    sizes = plan_pages(usable, style, full)
    recent = []   # templates of the last pages, for variety
    start = 0
    for number, size in enumerate(sizes):
        group = usable[start:start + size]
        start += size
        if size == 1 and group[0].name in full:
            name, order = "full", group
        else:
            name, order = _best_template(group, recent, False, style)
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


def _cover_choice(photos, cover):
    """The photo to put on the cover for the customer's choice, or None if it
    can't be used. Being a duplicate never blocks the cover (the owner's test:
    a new cover photo was also inside the album, so it was marked "duplicate")."""
    chosen = next((p for p in photos if p.name == cover), None)
    if chosen is None or chosen.grade != "skip":
        return chosen
    problems = set(getattr(chosen, "problems", []))
    if "duplicate" in problems:
        # Exactly the same photo twice: use the copy that was kept (same picture).
        kept = next((p for p in photos if p.name == getattr(chosen, "duplicate_of", None)), None)
        if kept is not None and kept.grade != "skip":
            return kept
    if problems and problems <= {"similar", "duplicate"}:
        return chosen   # an almost-identical shot: they chose this one, so use it
    return None


def page_count(count):
    """How many pages for this many photos: about 2.5 photos a page, an even
    number, within the printer's minimum and maximum (and 1-4 photos a page)."""
    pages = round(count / designs.PHOTOS_PER_PAGE)
    pages = max(designs.MIN_PAGES, min(designs.MAX_PAGES, pages))
    pages = max(math.ceil(count / 4), min(pages, count))
    if pages % designs.PAGE_MULTIPLE and pages + 1 <= count:
        pages += 1
    return pages


def pick_full_pages(photos, style, cover_photo=None):
    """The photos that get an edge-to-edge page of their own: about
    EDGE_TO_EDGE_SHARE of the pages, spread through the album. The best
    candidates: sharp, fill the page without cutting a face, with people."""
    if not style["full_page"]:
        return set()
    wanted = round(designs.EDGE_TO_EDGE_SHARE * page_count(len(photos)))
    page_aspect = designs.PAGE_WIDTH / designs.PAGE_HEIGHT

    def badness(photo):
        cut = _cut(photo, page_aspect, full_page=True)
        if photo.grade != "ok" or cut is None or photo.name == cover_photo:
            return None
        return _crop_loss(photo, page_aspect) + (0 if getattr(photo, "faces", None) else 0.15)

    chosen, last = set(), -99
    for part in range(wanted):
        # One from each part of the album, at least 3 photos after the last one.
        start = max(part * len(photos) // wanted, last + 3)
        end = (part + 1) * len(photos) // wanted
        options = [(badness(photos[i]), i) for i in range(start, end)
                   if badness(photos[i]) is not None]
        if options:
            _, last = min(options)
            chosen.add(photos[last].name)
    return chosen


def plan_pages(photos, style, full=()):
    """How many photos go on each page, in order (adds up to len(photos)).

    Tries every way to split the photos into the right number of pages with
    1-4 photos each, and keeps the one where the pages look best together
    (photos big, little cut, little empty background). Fast: the score of each
    possible page is worked out once."""
    count, pages = len(photos), page_count(len(photos))
    score = {}
    for start in range(count):
        for size in range(1, 5):
            if start + size <= count:
                group = photos[start:start + size]
                if any(p.name in full for p in group):
                    if size == 1:
                        score[start, size] = 0   # an edge-to-edge page: alone
                    continue
                score[start, size] = _best_choice(group, [], False, style)[0]
    # best[p][i, last] = (total score, size of the page before) for the first i
    # photos on p pages, the last page holding `last` photos.
    best = [{(0, 0): (0, 0)}]
    for p in range(1, pages + 1):
        row = {}
        for (i, last), (total, _) in best[p - 1].items():
            for size in range(1, 5):
                if (i + size) > count - (pages - p) or (i, size) not in score:
                    continue    # leave at least 1 photo for every page still to come
                new = total + score[i, size]
                if size == last:
                    new += REPEAT_COST   # variety: not the same number on every page
                key = (i + size, size)
                if key not in row or new < row[key][0]:
                    row[key] = (new, last)
        best.append(row)
    ends = [key for key in best[pages] if key[0] == count]
    if not ends:
        return plan_pages(photos, style)   # can't fit the edge-to-edge pages: plan without
    end = min(ends, key=lambda k: best[pages][k][0])
    sizes, (i, size) = [], end
    for p in range(pages, 0, -1):
        sizes.append(size)
        i, size = i - size, best[p][(i, size)][1]
    return sizes[::-1]


# ---------- choosing a template for one page ----------

def _best_template(group, recent, allow_full, style):
    """Returns (template name, photos in spot order)."""
    _, name, order = _best_choice(group, recent, allow_full, style)
    return name, order


def _best_choice(group, recent, allow_full, style):
    """Returns (score, template name, photos in spot order). Lower score = better."""
    best = None
    names = [n for n, spots in designs.TEMPLATES.items() if len(spots) == len(group)]
    names += [n for n, size in FLEX.items() if size == len(group)]
    for name in names:
        if name == "full" and not allow_full:
            continue
        fixed = None if name in FLEX else _spot_shapes(name, style)
        for order in _orders(group):
            shapes = fixed or _shapes(_flex_spots(name, order, style))
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
                    cost += 3 * loss + 0.3   # white gaps around it: avoid
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
    return best


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
    return _shapes(page.spots)


def _shapes(spots):
    return [(s.width / s.height, s.small, s.width, s.height) for s in spots]


# ---------- layouts that adapt to the photos' shapes ----------

def _flex_spots(name, photos, style):
    """Spots for a FLEX layout: each photo keeps its own shape, the photos
    touch with an even gap, and the whole block is as big as fits inside the
    margins, in the middle of the page."""
    margin, gap = style["margin"], style["gap"]
    inner_w = designs.PAGE_WIDTH - 2 * margin
    inner_h = designs.PAGE_HEIGHT - 2 * margin
    a = [p.width / p.height if p and p.width and p.height else 1 for p in photos]
    boxes = []   # (x, y, w, h) inside the block, left to right
    if name == "flex_row2":
        h = min((inner_w - gap) / (a[0] + a[1]), inner_h)
        boxes = [(0, 0, a[0] * h, h), (a[0] * h + gap, 0, a[1] * h, h)]
    elif name == "flex_col2":
        w = min((inner_h - gap) / (1 / a[0] + 1 / a[1]), inner_w)
        boxes = [(0, 0, w, w / a[0]), (0, w / a[0] + gap, w, w / a[1])]
    elif name == "flex_side3":
        k = 1 / (1 / a[1] + 1 / a[2])           # the 2-photo column's width per height
        h = min((inner_w - gap + gap * k) / (a[0] + k), inner_h)
        big_w, col_w = a[0] * h, (h - gap) * k
        boxes = [(0, 0, big_w, h), (big_w + gap, 0, col_w, col_w / a[1]),
                 (big_w + gap, col_w / a[1] + gap, col_w, col_w / a[2])]
    elif name == "flex_top3":
        both = a[1] + a[2]
        w = min((inner_h - gap + gap / both) / (1 / a[0] + 1 / both), inner_w)
        big_h, row_h = w / a[0], (w - gap) / both
        boxes = [(0, 0, w, big_h), (0, big_h + gap, a[1] * row_h, row_h),
                 (a[1] * row_h + gap, big_h + gap, a[2] * row_h, row_h)]
    elif name == "flex_grid4":
        top, bottom = a[0] + a[1], a[2] + a[3]
        w = min(gap + (inner_h - gap) / (1 / top + 1 / bottom), inner_w)
        h1, h2 = (w - gap) / top, (w - gap) / bottom
        boxes = [(0, 0, a[0] * h1, h1), (a[0] * h1 + gap, 0, a[1] * h1, h1),
                 (0, h1 + gap, a[2] * h2, h2), (a[2] * h2 + gap, h1 + gap, a[3] * h2, h2)]
    block_w = max(x + w for x, y, w, h in boxes)
    block_h = max(y + h for x, y, w, h in boxes)
    left = margin + (inner_w - block_w) / 2
    top = margin + (inner_h - block_h) / 2
    longest_page_side = max(designs.PAGE_WIDTH, designs.PAGE_HEIGHT)
    spots = []
    for photo, (x, y, w, h) in zip(photos, boxes):
        x = left + x
        if designs.RIGHT_TO_LEFT:
            x = designs.PAGE_WIDTH - x - w
        spots.append(Spot(photo=getattr(photo, "name", None), x=round(x, 2),
                          y=round(top + y, 2), width=round(w, 2), height=round(h, 2),
                          small=max(w, h) <= designs.SMALL_SPOT * longest_page_side))
    return spots


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

def _cut(photo, spot_aspect, full_page=False, cover=False):
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
    if cover:
        limit = MAX_CUT_COVER   # the cover may lose more, as long as every face stays in
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
    if name in FLEX:
        page.spots = _flex_spots(name, photos, style)
        for spot, photo in zip(page.spots, photos):
            _fit_photo(spot, photo)
        return page
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


# Where the cover title goes: this part of the page height, at the top or
# bottom of the photo. No face may be there.
TITLE_BAND = 0.22


def _cover(usable, style, title, chosen=None):
    """The front cover: the customer's chosen photo (or an early good photo)
    edge to edge, with the title on a band where there are no faces.
    Returns (page, title place)."""
    width, height = designs.PAGE_WIDTH, designs.PAGE_HEIGHT
    candidates = [chosen] if chosen else ([p for p in usable if p.grade == "ok"][:10]
                                          or usable[:1])
    for photo in candidates:
        cut = _cut(photo, width / height, full_page=True, cover=True)
        place = _title_place(photo, cut) if cut and title else "none"
        if cut and place:
            cover = Page("cover", style["cover_background"])
            cover.spots.append(Spot(photo=photo.name, x=0, y=0, width=width,
                                    height=height, small=False, crop=cut))
            return cover, place if title else "none"
    # No photo fits edge to edge without cutting a face: a smaller photo,
    # with the title under it.
    photo = candidates[0]
    margin = style["margin"] * 1.5
    text_height = height * 0.2 if title else 0
    cover = Page("cover", style["cover_background"])
    cover.spots.append(Spot(photo=photo.name, x=margin, y=margin, width=width - 2 * margin,
                            height=height - 2 * margin - text_height, small=False))
    _fit_photo(cover.spots[0], photo)
    return cover, "below"


def _title_place(photo, cut):
    """"bottom" or "top": where the title band covers no face. None if both would."""
    cx, cy, cw, ch = cut
    faces = [((y - cy) / ch, (y + h - cy) / ch) for x, y, w, h in getattr(photo, "faces", [])]
    if all(bottom <= 1 - TITLE_BAND for top, bottom in faces):
        return "bottom"
    if all(top >= TITLE_BAND for top, bottom in faces):
        return "top"
    return None
