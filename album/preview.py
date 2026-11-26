"""The customer's preview images (task 2.4).

The customer never gets the print PDF. They get small page images with a
"PREVIEW" mark across them, sent in WhatsApp:
  the cover, page 1, then two pages side by side as the open book shows them
  (pages 2-3, 4-5 …), then the last page. Page 1 and the last page are alone
  in the book, so they are shown on their own side of an open book, next to an
  empty grey half: every page is the same size (owner's feedback, Nov 24, 2026:
  a single page stretched to the full width looked twice as big).
Each page has its label under it ("עמוד 5", "כריכה"), so the customer can say
"page 5: …" when they want a change. Task 3.2: every photo inside the album has
a small number in its corner: the photo's own number (the order it was sent
in), so it never changes when the album is built again. The customer can then
replace or remove "photo 15". The numbers are on the previews only, never printed.
The cover has no number (it is changed with "change cover photo").
There is no second caption under the whole picture (owner's feedback,
Nov 24, 2026: the page numbers looked doubled).
The words come from the customer texts (server/texts/<language>.json:
preview_page, preview_cover).

They are small on purpose: a 20 cm page is 700 pixels (about 90 DPI), fine on
a phone screen, too blurry to print. Together with the mark, nobody can print
the album somewhere else from them.

build_album.py makes them from the screen-size page images, into the album's
folder: preview/00-cover.jpg, preview/01-page-1.jpg, preview/02-pages-2-3.jpg …

Needs Pillow (see requirements.txt).
"""

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import render

FOLDER = "preview"
PAGE_PIXELS = 700          # the long side of one page in a preview
GAP = 6                    # pixels between the two pages of a spread (the book's fold)
NUMBER_STRIP = 46          # pixels under the pages for the page numbers
BACKGROUND = (236, 236, 236)
EMPTY_SIDE = (222, 222, 222)   # the inside of the cover, next to page 1 and the last page
NUMBER_COLOUR = (90, 90, 90)
MARK = "PREVIEW"
MARK_OPACITY = 70          # 0-255: see-through, but can't be missed
MARK_SIZE = 0.15           # letter height, as a part of the page's height
FONT = Path(__file__).resolve().parent / "fonts" / "Rubik.ttf"
TEXTS_DIR = Path(__file__).resolve().parent.parent / "server" / "texts"
QUALITY = 80
# The photo numbers (task 3.2): a dark round badge with a white number, in the
# photo's top right corner (where a Hebrew reader looks first). Owner's phone
# test (Nov 26, 2026): 34 pixels was too small to read on a phone, where a
# two-page picture is shrunk to the screen's width; now about twice as big, bold.
BADGE_SIZE = 66            # pixels across, on a 700-pixel page
BADGE_INSET = 10           # pixels from the photo's corner
BADGE_COLOUR = (35, 35, 35, 215)


def photo_number(name):
    """The number of a photo from an order ("photo 015" -> 15), or None."""
    match = re.fullmatch(r"photo (\d+)", name or "")
    return int(match.group(1)) if match else None


def spreads(page_count):
    """Which pages go in each preview image, in order. None = the cover.
    In a Hebrew book page 1 is alone on the left, then 2|3, 4|5 … and the last
    page (an even number) alone on the right."""
    groups = [[None], [1]]
    for first in range(2, page_count + 1, 2):
        groups.append([n for n in (first, first + 1) if n <= page_count])
    return groups


def labels(language="he"):
    """The words under the pages: (cover label, page label with {page})."""
    texts = json.loads((TEXTS_DIR / f"{language}.json").read_text(encoding="utf-8"))
    return texts["preview_cover"], texts["preview_page"]


def make_previews(folder, page_count, language="he", album=None, numbers=None):
    """Make the preview images from the album's cover.jpg and page-NN.jpg.
    album (layout.Album) and numbers ({photo name: number}): put each photo's
    number on it (task 3.2). Without them, the pages have no numbers.
    Returns [{"file": full path, "pages": [2, 3]}, …] ("pages": [] for the cover)."""
    folder = Path(folder)
    cover_label, page_label = labels(language)
    out = folder / FOLDER
    out.mkdir(exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()   # from an earlier build of this album

    made = []
    for index, group in enumerate(spreads(page_count)):
        if group == [None]:
            pages, files, name = [], ["cover.jpg"], "cover"
        else:
            pages = group
            files = [f"page-{n:02d}.jpg" for n in group]
            name = (f"page-{group[0]}" if len(group) == 1
                    else f"pages-{group[0]}-{group[-1]}")
        images = [Image.open(folder / file).convert("RGB") for file in files]
        badges = [_badges(album, numbers, n) for n in pages] if pages else [[]]
        image = _spread(images, pages, cover_label, page_label, badges)
        path = out / f"{index:02d}-{name}.jpg"
        image.save(path, "JPEG", quality=QUALITY)
        made.append({"file": str(path), "pages": pages})
    return made


def _badges(album, numbers, page_number):
    """[(number, (x, y, width, height) as parts of the page)] for the photos
    on one page of the album."""
    if album is None or not numbers or page_number > len(album.pages):
        return []
    page = album.pages[page_number - 1]
    return [(numbers[s.photo], (s.x / album.width, s.y / album.height,
                                s.width / album.width, s.height / album.height))
            for s in page.spots if s.photo in numbers]


def _spread(images, numbers, cover_label, page_label, badges=None):
    """The pages side by side, right to left (like a Hebrew book), each with
    the mark, and its label ("עמוד 5", or "כריכה" for the cover) underneath."""
    badges = badges or [[] for _ in images]
    pages = [add_numbers(watermark(_shrink(image)), spots)
             for image, spots in zip(images, badges)]
    if len(numbers or []) == 1:
        # A page alone in the book: odd pages are on the left, even on the right.
        empty = Image.new("RGB", pages[0].size, EMPTY_SIDE)
        if numbers[0] % 2:
            pages, numbers = [empty] + pages, [None] + numbers
        else:
            pages, numbers = pages + [empty], numbers + [None]
    height = max(p.height for p in pages)
    width = sum(p.width for p in pages) + GAP * (len(pages) - 1)
    strip = NUMBER_STRIP
    sheet = Image.new("RGB", (width, height + strip), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    # Same simple letter drawing as the cover title (render.py), so Hebrew
    # comes out right to left on every Mac.
    font = ImageFont.truetype(str(FONT), round(NUMBER_STRIP * 0.5),
                              layout_engine=ImageFont.Layout.BASIC)
    names = ([page_label.format(page=n) if n is not None else None for n in numbers]
             if numbers else [cover_label])
    x = width
    for page, name in zip(pages, names):
        # The first page of the group is on the right.
        x -= page.width
        sheet.paste(page, (x, 0))
        if name is not None:   # None: the empty grey side next to a page alone
            draw.text((x + page.width / 2, height + strip / 2), render.visual_order(name),
                      fill=NUMBER_COLOUR, font=font, anchor="mm")
        x -= GAP
    return sheet


def _shrink(image):
    scale = PAGE_PIXELS / max(image.size)
    if scale >= 1:
        return image
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.Resampling.LANCZOS)


def add_numbers(page, badges):
    """A small round badge with the photo's number in each photo's top right
    corner. badges: [(number, (x, y, width, height) as parts of the page)]."""
    if not badges:
        return page
    layer = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    scale = max(page.size) / PAGE_PIXELS
    size, inset = round(BADGE_SIZE * scale), round(BADGE_INSET * scale)
    for number, (x, y, w, h) in badges:
        right, top = round((x + w) * page.width) - inset, round(y * page.height) + inset
        box = (right - size, top, right, top + size)
        draw.ellipse(box, fill=BADGE_COLOUR, outline=(255, 255, 255, 220),
                     width=max(1, round(scale * 1.5)))
        text = str(number)
        font = _bold(round(size * (0.58 if len(text) < 3 else 0.46)))
        draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, font=font,
                  anchor="mm", fill="white")
    marked = page.convert("RGBA")
    marked.alpha_composite(layer)
    return marked.convert("RGB")


def _bold(size):
    """Rubik in bold (the font file holds all its weights)."""
    font = ImageFont.truetype(str(FONT), size)
    try:
        font.set_variation_by_name("Bold")
    except (OSError, ValueError):
        pass   # an older Pillow: regular weight
    return font


def watermark(page):
    """The word PREVIEW across the page, slanted, in see-through white with a
    dark edge, so it shows on light and dark photos alike."""
    side = round(max(page.size) * 1.5)
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = ImageFont.truetype(str(FONT), round(page.height * MARK_SIZE))
    edge = max(1, round(page.height * 0.003))
    # Three rows of the word, so cropping out one part of the page doesn't help.
    for row in (0.3, 0.5, 0.7):
        draw.text((side / 2, side * row), MARK, font=font, anchor="mm",
                  fill=(255, 255, 255, MARK_OPACITY),
                  stroke_width=edge, stroke_fill=(0, 0, 0, MARK_OPACITY // 2))
    layer = layer.rotate(35, resample=Image.Resampling.BICUBIC)
    left, top = (side - page.width) // 2, (side - page.height) // 2
    layer = layer.crop((left, top, left + page.width, top + page.height))
    marked = page.convert("RGBA")
    marked.alpha_composite(layer)
    return marked.convert("RGB")
