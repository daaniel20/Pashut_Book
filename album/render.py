"""Draw the album's pages as images (task 2.2).

Takes the plan from layout.py and the photos, and draws each page.
For now it makes screen-size page images for the owner to look at.
The same drawing at print resolution becomes the print PDF in task 2.3,
and small copies with a "PREVIEW" mark become the customer's previews in 2.4.

Needs Pillow (see requirements.txt).
"""

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


def draw_page(page, album, photos, pixels_per_mm):
    """One page as an image."""
    style = designs.DESIGNS[album.design]
    size = (round(album.width * pixels_per_mm), round(album.height * pixels_per_mm))
    image = Image.new("RGB", size, page.background)
    for spot in page.spots:
        # A photo from edge to edge (full page, cover) has no frame or rounded corners.
        _draw_photo(image, spot, photos, style, pixels_per_mm,
                    framed=spot.x > 0 or spot.y > 0)
    if page.template == "cover" and album.title:
        _draw_title(image, album, style, pixels_per_mm)
    return image


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
# of the photo). White letters with a soft shadow; dark letters on a very
# bright part of the photo (sky, a white wall).
TITLE_TEXT_HEIGHT = 0.5      # the letters use this part of the title area's height
BRIGHT = 170                 # brighter than this (0-255) behind the title: dark letters


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
    lines, font = _fit_text(album.title, style, box_w, box_h * height_used)
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
    behind = image.crop((int(left), int(top), int(right), int(bottom))).convert("L")
    bright = ImageStat.Stat(behind).mean[0] > BRIGHT
    letters, shade = ((34, 34, 34), (255, 255, 255, 150)) if bright else \
                     ((255, 255, 255), (0, 0, 0, 160))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    for (x, y), text in places:
        draw.text((x, y + font.size * 0.03), text, font=font, fill=shade)
    shadow = shadow.filter(ImageFilter.GaussianBlur(font.size * 0.08))
    image.paste(Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB"))
    draw = ImageDraw.Draw(image)
    for xy, text in places:
        draw.text(xy, text, font=font, fill=letters)


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
