"""The customer's preview images (task 2.4).

The customer never gets the print PDF. They get small page images with a
"PREVIEW" mark across them, sent in WhatsApp:
  the cover, page 1, then two pages side by side as the open book shows them
  (pages 2-3, 4-5 …), then the last page.
Each image has the page numbers under the pages, so the customer can say
"page 5: …" when they want a change.

They are small on purpose: a 20 cm page is 700 pixels (about 90 DPI), fine on
a phone screen, too blurry to print. Together with the mark, nobody can print
the album somewhere else from them.

build_album.py makes them from the screen-size page images, into the album's
folder: preview/00-cover.jpg, preview/01-page-1.jpg, preview/02-pages-2-3.jpg …

Needs Pillow (see requirements.txt).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FOLDER = "preview"
PAGE_PIXELS = 700          # the long side of one page in a preview
GAP = 6                    # pixels between the two pages of a spread (the book's fold)
NUMBER_STRIP = 46          # pixels under the pages for the page numbers
BACKGROUND = (236, 236, 236)
NUMBER_COLOUR = (90, 90, 90)
MARK = "PREVIEW"
MARK_OPACITY = 70          # 0-255: see-through, but can't be missed
MARK_SIZE = 0.15           # letter height, as a part of the page's height
FONT = Path(__file__).resolve().parent / "fonts" / "Rubik.ttf"
QUALITY = 80


def spreads(page_count):
    """Which pages go in each preview image, in order. None = the cover.
    In a Hebrew book page 1 is alone on the left, then 2|3, 4|5 … and the last
    page (an even number) alone on the right."""
    groups = [[None], [1]]
    for first in range(2, page_count + 1, 2):
        groups.append([n for n in (first, first + 1) if n <= page_count])
    return groups


def make_previews(folder, page_count):
    """Make the preview images from the album's cover.jpg and page-NN.jpg.
    Returns [{"file": full path, "pages": [2, 3]}, …] ("pages": [] for the cover)."""
    folder = Path(folder)
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
        image = _spread(images, pages)
        path = out / f"{index:02d}-{name}.jpg"
        image.save(path, "JPEG", quality=QUALITY)
        made.append({"file": str(path), "pages": pages})
    return made


def _spread(images, numbers):
    """The pages side by side, right to left (like a Hebrew book), each with
    the mark, and their numbers underneath."""
    pages = [watermark(_shrink(image)) for image in images]
    height = max(p.height for p in pages)
    width = sum(p.width for p in pages) + GAP * (len(pages) - 1)
    strip = NUMBER_STRIP if numbers else 0
    sheet = Image.new("RGB", (width, height + strip), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONT), round(NUMBER_STRIP * 0.55))
    x = width
    for page, number in zip(pages, numbers or [None] * len(pages)):
        # The first page of the group is on the right.
        x -= page.width
        sheet.paste(page, (x, 0))
        if number is not None:
            draw.text((x + page.width / 2, height + strip / 2), str(number),
                      fill=NUMBER_COLOUR, font=font, anchor="mm")
        x -= GAP
    return sheet


def _shrink(image):
    scale = PAGE_PIXELS / max(image.size)
    if scale >= 1:
        return image
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.Resampling.LANCZOS)


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
