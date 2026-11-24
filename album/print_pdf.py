"""Make the print PDF of an album (task 2.3).

First build the album and look at it (build_album.py). Then, run from the
project folder, with the project's Python (.venv):

  .venv/bin/python album/print_pdf.py --order latest
      the print files of the newest order (or give an order ID)

  .venv/bin/python album/print_pdf.py ~/Desktop/test-photos
      the print files of an album built from a folder

  Add --json to print the result as one line of data (the bot uses this when
  it asks the owner to approve the album, task 3.1).

It draws exactly the pages in layout.json (what the owner saw), at print
resolution and with bleed, using the rules in printer.py. The files go next
to the album, in output/albums/<name>/:
  print-pages.pdf   the inside pages, in reading order (page 1, 2, 3 …)
  print-cover.pdf   the front cover (when the printer wants it separately)
It also checks every photo's print resolution and warns about weak ones.

🔒 The print PDF is for the printer only. Never send it to the customer.
"""

import json
import sys
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

import designs
import layout
import printer
import render
from build_album import OUTPUT_DIR, order_photos
from check_photos import photos_from_folder

MM_PER_INCH = 25.4


def make_print_files(album, photos, folder):
    """Write the print PDFs for this album (a layout.Album) into folder.
    photos: list of (name, bytes). Returns a report (dict)."""
    data = dict(photos)
    missing = sorted({s.photo for p in [album.cover] + album.pages for s in p.spots
                      if s.photo not in data})
    if missing:
        raise ValueError(f"Photos missing for this album: {', '.join(missing)}")
    box = render.PhotoBox(photos)
    ppm = printer.DPI / MM_PER_INCH
    for old in folder.glob("print-*.pdf"):
        old.unlink()

    def inside(page):
        return render.draw_page(page, album, box, ppm, printer.BLEED)

    def cover():
        return render.draw_page(album.cover, album, box, ppm, printer.COVER_BLEED)

    files = []
    if printer.COVER_SEPARATE:
        files.append(_write_pdf(folder / "print-cover.pdf", [cover], album,
                                printer.COVER_BLEED))
        pages = [lambda p=p: inside(p) for p in album.pages]
    else:
        # One file: the cover is page 1 (with the inside pages' bleed).
        pages = [lambda p=p: inside(p) for p in [album.cover] + album.pages]
    files.append(_write_pdf(folder / "print-pages.pdf", pages, album, printer.BLEED))

    problems, warnings = check_resolution(album, data)
    count = len(album.pages)
    if count % designs.PAGE_MULTIPLE:
        problems.append(f"{count} pages: the printer needs a multiple of "
                        f"{designs.PAGE_MULTIPLE}.")
    if not designs.MIN_PAGES <= count <= designs.MAX_PAGES:
        problems.append(f"{count} pages: the book must have "
                        f"{designs.MIN_PAGES}-{designs.MAX_PAGES}.")
    return {"files": [str(f) for f in files], "pages": count,
            "page_size_mm": [album.width, album.height], "bleed_mm": printer.BLEED,
            "dpi": printer.DPI, "problems": problems, "warnings": warnings}


def check_resolution(album, data):
    """Each photo's print resolution in its spot (dots per inch). Returns
    (problems, warnings): photos below LOW_DPI, and below GOOD_DPI."""
    sizes = {}
    problems, warnings = [], []
    places = [("cover", album.cover)] + [(f"page {n}", p) for n, p in enumerate(album.pages, 1)]
    for place, page in places:
        for spot in page.spots:
            if spot.photo not in sizes:
                sizes[spot.photo] = _pixel_size(data[spot.photo])
            width, height = sizes[spot.photo]
            _, _, cw, ch = spot.crop
            dpi = min(width * cw / (spot.width / MM_PER_INCH),
                      height * ch / (spot.height / MM_PER_INCH))
            if dpi < printer.LOW_DPI:
                problems.append(f"{place}: {spot.photo} prints at only {dpi:.0f} DPI "
                                "(will look blurry), use a smaller spot or another photo.")
            elif dpi < printer.GOOD_DPI:
                warnings.append(f"{place}: {spot.photo} prints at {dpi:.0f} DPI "
                                "(may look a little soft up close).")
    return problems, warnings


def _pixel_size(data):
    """The photo's size in pixels, turned the right way up (reads only the header)."""
    image = Image.open(BytesIO(data))
    turned = image.getexif().get(0x0112, 1) in (5, 6, 7, 8)   # photo taken sideways
    return (image.height, image.width) if turned else image.size


# ---------- a small PDF writer ----------
# Pillow can save a PDF too, but it keeps every page in memory (40 pages at
# print size is too much for comfort) and doesn't mark the trim size.
# This writes one page at a time: each page is a JPEG picture filling the page.
# TrimBox tells the printer where to cut (the page without the bleed).

def _write_pdf(path, pages, album, bleed):
    """pages: functions that each draw one page (so only one is in memory)."""
    points = 72 / MM_PER_INCH
    full_w = (album.width + 2 * bleed) * points
    full_h = (album.height + 2 * bleed) * points
    trim = [bleed * points, bleed * points, full_w - bleed * points, full_h - bleed * points]
    offsets = []
    with open(path, "wb") as out:
        def obj(number, body, stream=None):
            offsets.append((number, out.tell()))
            out.write(f"{number} 0 obj\n".encode())
            out.write(body.encode())
            if stream is not None:
                out.write(b"\nstream\n" + stream + b"\nendstream")
            out.write(b"\nendobj\n")

        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        count = len(pages)
        page_ids = [5 + 3 * i for i in range(count)]
        obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
        obj(2, f"<< /Type /Pages /Count {count} /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] >>")
        title = (album.title or "Pashut Book album").encode("utf-16-be").hex()
        obj(3, f"<< /Producer (Pashut Book) /Title <feff{title}> >>")
        icc = _srgb_profile()
        obj(4, f"<< /N 3 /Length {len(icc)} /Filter /FlateDecode >>", icc)
        box = " ".join(f"{v:.3f}" for v in [0, 0, full_w, full_h])
        trim_box = " ".join(f"{v:.3f}" for v in trim)
        for page_id, draw in zip(page_ids, pages):
            image = draw()
            buffer = BytesIO()
            image.save(buffer, "JPEG", quality=printer.JPEG_QUALITY, subsampling=0,
                       dpi=(printer.DPI, printer.DPI))
            jpeg = buffer.getvalue()
            content = f"q {full_w:.3f} 0 0 {full_h:.3f} 0 0 cm /Photo Do Q".encode()
            obj(page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [{box}] "
                         f"/BleedBox [{box}] /TrimBox [{trim_box}] "
                         f"/Resources << /XObject << /Photo {page_id + 1} 0 R >> >> "
                         f"/Contents {page_id + 2} 0 R >>")
            obj(page_id + 1, f"<< /Type /XObject /Subtype /Image /Width {image.width} "
                             f"/Height {image.height} /ColorSpace [/ICCBased 4 0 R] "
                             f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>",
                jpeg)
            obj(page_id + 2, f"<< /Length {len(content)} >>", content)
        xref = out.tell()
        offsets.sort()
        out.write(f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode())
        for _, offset in offsets:
            out.write(f"{offset:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R /Info 3 0 R >>\n"
                  f"startxref\n{xref}\n%%EOF\n".encode())
    return path


def _srgb_profile():
    """The standard screen colours (sRGB), so the printer knows what the
    colours mean. Our photos and page colours are all sRGB."""
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return zlib.compress(profile)


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) == 2 and args[0] == "--order":
        order, photos = order_photos(args[1])
        folder = OUTPUT_DIR / order["id"][:8]
    elif len(args) == 1 and not args[0].startswith("--"):
        photos = photos_from_folder(args[0])
        folder = OUTPUT_DIR / Path(args[0]).expanduser().name
    else:
        sys.exit(__doc__)
    plan = folder / "layout.json"
    if not plan.exists():
        sys.exit(f"❌ No album in {folder}. Build it first with album/build_album.py.")
    album = layout.Album.from_dict(json.loads(plan.read_text(encoding="utf-8")))
    print(f"Making the print PDF: {len(album.pages)} pages, {album.width:g}x{album.height:g} mm "
          f"+ {printer.BLEED} mm bleed, {printer.DPI} DPI…", file=sys.stderr)
    try:
        report = make_print_files(album, photos, folder)
    except ValueError as error:
        if as_json:
            print(json.dumps({"error": str(error)}, ensure_ascii=False))
            return
        sys.exit(f"❌ {error}")
    if as_json:
        print(json.dumps(dict(report, notes=album.notes), ensure_ascii=False))
        return
    for problem in report["problems"]:
        print(f"❌ {problem}")
    for warning in report["warnings"]:
        print(f"⚠️ {warning}")
    for file in report["files"]:
        size = Path(file).stat().st_size / 1_000_000
        print(f"✅ {file}  ({size:.0f} MB)")
    print("🔒 For the printer only. Never send the print PDF to the customer.")


if __name__ == "__main__":
    main()
