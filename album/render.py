"""Draw the album's pages as images (task 2.2).

Takes the plan from layout.py and the photos, and draws each page.
It makes screen-size page images for the owner to look at. The same
drawing at print resolution, with bleed, becomes the print PDF (print_pdf.py,
task 2.3), and small copies with a "PREVIEW" mark become the customer's previews in 2.4.

Needs Pillow (see requirements.txt).
"""

import unicodedata
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

import designs
import layout

try:
    from pillow_heif import register_heif_opener   # iPhone photos (HEIC)
    register_heif_opener()
except ImportError:
    pass

class PhotoBox:
    """Opens each photo only when needed, already shrunk, so 100 big photos
    don't fill the computer's memory."""

    def __init__(self, photos):
        self.data = dict(photos)   # name -> the photo's bytes

    def open(self, name, width, height, crop=(0, 0, 1, 1)):
        """The part of the photo chosen by layout.py (crop), at this size in pixels."""
        cx, cy, cw, ch = crop
        image = Image.open(BytesIO(self.data[name]))
        # JPEG: decode at a smaller size (fast). Photos turned sideways swap sizes.
        need = (round(width / cw), round(height / ch))
        image.draft("RGB", (max(need), max(need)))
        image = ImageOps.exif_transpose(image).convert("RGB")
        box = (round(cx * image.width), round(cy * image.height),
               round((cx + cw) * image.width), round((cy + ch) * image.height))
        return image.crop(box).resize((width, height), Image.Resampling.LANCZOS)


def draw_page(page, album, photos, pixels_per_mm, bleed=0):
    """One page as an image. bleed (mm): extra picture around the page for the
    printer to cut off (task 2.3). The background, and photos that reach the
    edge, continue into it; everything else stays where it was."""
    style = designs.DESIGNS[album.design]
    size = (round((album.width + 2 * bleed) * pixels_per_mm),
            round((album.height + 2 * bleed) * pixels_per_mm))
    image = Image.new("RGB", size, page.background)
    for spot in page.spots:
        # A photo from edge to edge (full page, cover) has no frame or rounded corners.
        framed = spot.x > 0 or spot.y > 0
        if bleed:
            spot = with_bleed(spot, album.width, album.height, bleed)
        _draw_photo(image, spot, photos, style, pixels_per_mm, framed=framed)
    if page.template == "cover" and album.title:
        # The title is placed on the page itself (without the bleed).
        offset = round(bleed * pixels_per_mm)
        inside = image.crop((offset, offset, image.width - offset, image.height - offset))
        _draw_title(inside, album, style, pixels_per_mm)
        image.paste(inside, (offset, offset))
    return image


EDGE = 0.05   # mm: a spot this close to the page's edge touches it


def with_bleed(spot, page_width, page_height, bleed):
    """The spot moved by the bleed (the image is bigger), and stretched into the
    bleed on every side that touches the page's edge. It shows a little more of
    the photo there; if the photo has no more to show, it is zoomed in a little
    (3 mm on a 20 cm page is 3%), never stretched out of shape."""
    grow_left = bleed if spot.x <= EDGE else 0
    grow_top = bleed if spot.y <= EDGE else 0
    grow_right = bleed if spot.x + spot.width >= page_width - EDGE else 0
    grow_bottom = bleed if spot.y + spot.height >= page_height - EDGE else 0
    cx, cy, cw, ch = spot.crop
    per_mm_x, per_mm_y = cw / spot.width, ch / spot.height
    x0, x1 = cx - grow_left * per_mm_x, cx + cw + grow_right * per_mm_x
    y0, y1 = cy - grow_top * per_mm_y, cy + ch + grow_bottom * per_mm_y
    # Too big for the photo: show a smaller part (same shape), around the same middle.
    shrink = min(1, 1 / (x1 - x0), 1 / (y1 - y0))
    if shrink < 1:
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        half_w, half_h = (x1 - x0) * shrink / 2, (y1 - y0) * shrink / 2
        x0, x1, y0, y1 = mid_x - half_w, mid_x + half_w, mid_y - half_h, mid_y + half_h
    # Slide it back inside the photo.
    move_x = max(0, -x0) - max(0, x1 - 1)
    move_y = max(0, -y0) - max(0, y1 - 1)
    x0, x1, y0, y1 = x0 + move_x, x1 + move_x, y0 + move_y, y1 + move_y
    return layout.Spot(
        photo=spot.photo, small=spot.small,
        x=spot.x + bleed - grow_left, y=spot.y + bleed - grow_top,
        width=spot.width + grow_left + grow_right,
        height=spot.height + grow_top + grow_bottom,
        crop=(max(0, x0), max(0, y0), min(1, x1) - max(0, x0), min(1, y1) - max(0, y0)))


def _draw_photo(image, spot, photos, style, ppm, framed):
    x, y = round(spot.x * ppm), round(spot.y * ppm)
    w, h = round(spot.width * ppm), round(spot.height * ppm)
    border = round(style["border"] * ppm) if framed else 0
    corner = round(style["corner"] * ppm) if framed else 0
    draw = ImageDraw.Draw(image)
    if border:
        # A white frame around the photo, the photo inside it.
        draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=corner, fill="white")
        x, y, w, h = x + border, y + border, w - 2 * border, h - 2 * border
        corner = max(0, corner - border)
    photo = photos.open(spot.photo, w, h, spot.crop)
    mask = None
    if corner:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=corner, fill=255)
    image.paste(photo, (x, y), mask)


# The cover title over the photo: no band (owner's feedback: the band hid part
# of the photo). Always white letters with a soft shadow. Where the photo behind
# the title is bright or busy, a soft dark fade from the edge of the cover makes
# them readable. (Task 1.2b, owner's test: the old rule, dark letters on a bright
# area, made the title vanish on a bright rug with black stripes.)
TITLE_TEXT_HEIGHT = 0.5      # the letters use this part of the title area's height
FADE_BRIGHT = 120            # brighter than this (0-255, on average) behind the title: fade
FADE_BUSY = 45               # or busier than this (how much it varies): fade
FADE_DARKEST = 200           # the fade at the cover's edge (0-255; 255 = black)
FADE_REACH = 2.2             # the fade covers this many times the title area, then is gone


def _draw_title(image, album, style, ppm):
    """The cover title: straight on the photo (top or bottom, where there are
    no faces), or in the space under a smaller photo."""
    photo_spot = album.cover.spots[0]
    on_photo = album.title_place in ("top", "bottom")
    if on_photo:
        area = layout.TITLE_BAND * album.height * ppm
        top = 0 if album.title_place == "top" else image.height - area
        bottom = top + area
        left, right = style["margin"] * 2 * ppm, image.width - style["margin"] * 2 * ppm
        height_used = TITLE_TEXT_HEIGHT
    else:
        top = (photo_spot.y + photo_spot.height) * ppm
        bottom = (album.height - photo_spot.y) * ppm
        left, right = photo_spot.x * ppm, (album.width - photo_spot.x) * ppm
        height_used = 0.8
    box_w, box_h = right - left, bottom - top
    title = printable(album.title)
    if not title:
        return
    lines, font = _fit_text(title, style, box_w, box_h * height_used)
    line_h = font.size * 1.25
    places = []
    y = top + (box_h - line_h * len(lines)) / 2
    for line in lines:
        text = visual_order(line)
        width = ImageDraw.Draw(image).textlength(text, font=font)
        places.append(((left + (box_w - width) / 2, y), text))
        y += line_h
    if not on_photo:
        draw = ImageDraw.Draw(image)
        for xy, text in places:
            draw.text(xy, text, font=font, fill=style["title_color"])
        return
    behind = ImageStat.Stat(image.crop((int(left), int(top), int(right), int(bottom))).convert("L"))
    if behind.mean[0] > FADE_BRIGHT or behind.stddev[0] > FADE_BUSY:
        _fade(image, top, bottom, album.title_place == "top")
    letters, shade = (255, 255, 255), (0, 0, 0, 170)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    for (x, y), text in places:
        draw.text((x, y + font.size * 0.03), text, font=font, fill=shade)
    shadow = shadow.filter(ImageFilter.GaussianBlur(font.size * 0.08))
    image.paste(Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB"))
    draw = ImageDraw.Draw(image)
    for xy, text in places:
        draw.text(xy, text, font=font, fill=letters)


def _fade(image, top, bottom, at_top):
    """Darken the cover softly from its edge (top or bottom) toward the middle,
    behind the title: strongest at the edge, gone FADE_REACH title areas in."""
    reach = int((bottom - top) * FADE_REACH)
    column = Image.new("L", (1, reach))
    for i in range(reach):
        from_edge = i / reach                  # 0 at the cover's edge, 1 where it's gone
        column.putpixel((0, i), int(FADE_DARKEST * (1 - from_edge) ** 1.6))
    if not at_top:
        column = column.transpose(Image.FLIP_TOP_BOTTOM)
    mask = column.resize((image.width, reach))
    y = 0 if at_top else image.height - reach
    image.paste((0, 0, 0), (0, y, image.width, y + reach), mask)


def printable(text):
    """Drop emojis and symbols the font can't draw (they'd print as an empty box).
    The bot already removes them when the customer types the title; this also
    covers titles given by hand (--title)."""
    kept = "".join(c for c in text if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co")
                   and c not in "\ufe0e\ufe0f\u200d\u20e3")
    return " ".join(kept.split())


def _fit_text(text, style, width, height):
    """The biggest font size at which the text fits, on 1 or 2 lines."""
    words = text.split()
    choices = [[text]]
    if len(words) > 1:
        # Two lines, split near the middle.
        middle = min(range(1, len(words)),
                     key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        choices.append([" ".join(words[:middle]), " ".join(words[middle:])])
    best = None
    for lines in choices:
        size = int(height / (1.25 * len(lines)))
        while size > 8:
            font = _font(style, size)
            if max(font.getlength(visual_order(line)) for line in lines) <= width:
                break
            size = int(size * 0.92)
        if best is None or size > best[1].size:
            best = (lines, _font(style, size))
    return best


def _font(style, size):
    # The basic layout draws letters one by one; visual_order() puts Hebrew
    # in the right order first, so it works on every Mac the same way.
    font = ImageFont.truetype(str(style["font"]), size, layout_engine=ImageFont.Layout.BASIC)
    try:
        font.set_variation_by_name(style["font_weight"])
    except (OSError, ValueError):
        pass
    return font


def visual_order(text):
    """Put right-to-left text (Hebrew, Arabic) in the order it is drawn on the
    page, left to right. Numbers and English words inside it stay readable:
    "החופשה באילת 2026" is drawn as "2026 תליאב השפוחה"."""
    kinds = [_is_rtl(char) for char in text]
    # Spaces and marks between two English words/numbers are part of them;
    # anywhere else they follow the Hebrew.
    for i, kind in enumerate(kinds):
        if kind is None:
            before = next((k for k in reversed(kinds[:i]) if k is not None), True)
            after = next((k for k in kinds[i + 1:] if k is not None), True)
            kinds[i] = before or after
    runs = []   # [is_rtl, characters]
    for char, rtl in zip(text, kinds):
        if runs and runs[-1][0] == rtl:
            runs[-1][1].append(char)
        else:
            runs.append([rtl, [char]])
    if not any(_is_rtl(char) for char in text):
        return text                       # no Hebrew: leave as it is
    out = []
    for rtl, chars in reversed(runs):
        part = "".join(chars)
        if rtl:
            out.append(_mirror_brackets(part[::-1]))
        else:
            out.append(part)
    return "".join(out).strip()


def _is_rtl(char):
    code = ord(char)
    if 0x0590 <= code <= 0x08FF or 0xFB1D <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
        return True
    if char.isalnum():
        return False
    return None


def _mirror_brackets(text):
    return text.translate(str.maketrans("()[]{}<>", ")(][}{><"))
