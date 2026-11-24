"""Build a whole album automatically (task 2.2).

Run from the project folder, with the project's Python (.venv):

  .venv/bin/python album/build_album.py ~/Desktop/test-photos
      builds an album from the photos in a folder

  .venv/bin/python album/build_album.py --order latest
      builds the album of the newest order in Supabase (or give an order ID),
      with the design and cover title the customer chose

  Extra options:
    --design classic|colorful   choose the design (default: the order's, or classic)
    --title "החופשה באילת"      a cover title (default: the order's, or none)
    --cover 012.jpg             the photo for the cover (default: the one the
                                customer chose, or the first good photo)
    --check                     only check the photos, don't build (the bot uses this)
    --json                      print the result as one line of data (for the bot)

It checks the photos (quality.py), plans the pages (layout.py) and draws them
(render.py). The result goes to output/albums/<name>/ on this Mac only:
  album.html     open it to see the whole album as a book
  cover.jpg, page-01.jpg …   the pages (screen size, not for print)
  layout.json    the plan: which photo is where (used by the print PDF)
  preview/       the customer's small images with a PREVIEW mark (task 2.4)

When the album looks right, make the print files with album/print_pdf.py (2.3).
"""

import base64
import html
import json
import sys
from io import BytesIO
from pathlib import Path

import designs
import layout
import preview
import quality
import render
from check_photos import photos_from_folder, PROJECT_DIR

OUTPUT_DIR = PROJECT_DIR / "output" / "albums"
PREVIEW_PIXELS_PER_MM = 5      # a 20 cm page = 1000 pixels: fine for a screen


def summary(results):
    """Counts the bot needs to tell the customer about their photos."""
    left_out = {"blurry": 0, "duplicate": 0, "unusable": 0}
    for r in results:
        if r.grade == "skip":
            left_out[left_out_reason(r)] += 1
    readable = [r for r in results if "unreadable" not in r.problems]
    return {
        "photos": len(results),
        "used": sum(r.grade != "skip" for r in results),
        "left_out": left_out,
        "without_hd": sum(r.long_side == quality.WITHOUT_HD_PIXELS for r in readable),
    }


def left_out_reason(result):
    if {"unreadable", "too_small"} & set(result.problems):
        return "unusable"
    if {"duplicate", "similar"} & set(result.problems):
        return "duplicate"
    return "blurry"


def build(photos, design, title, folder, cover=None, cover_kept=False):
    """Check, plan and draw an album. photos is a list of (name, bytes).
    cover_kept: the customer was told the cover photo is blurry or small and kept it."""
    results = quality.check_all(photos)
    info = summary(results)
    album = layout.make_album(results, design, title, cover, cover_kept)
    box = render.PhotoBox(photos)
    folder.mkdir(parents=True, exist_ok=True)
    for old in [*folder.glob("*.jpg"), *folder.glob("print-*.pdf")]:
        old.unlink()   # pages and print files from an earlier build of this album

    files = ["cover.jpg"]
    _save(render.draw_page(album.cover, album, box, PREVIEW_PIXELS_PER_MM), folder / files[0])
    for number, page in enumerate(album.pages, start=1):
        files.append(f"page-{number:02d}.jpg")
        _save(render.draw_page(page, album, box, PREVIEW_PIXELS_PER_MM), folder / files[-1])

    (folder / "layout.json").write_text(
        json.dumps(album.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    _write_overview(folder, album, files, results, photos)
    previews = preview.make_previews(folder, len(album.pages))
    in_album = {s.photo for page in [album.cover] + album.pages for s in page.spots if s.photo}
    info.update(pages=len(album.pages), design=design, folder=str(folder),
                notes=album.notes, previews=previews, photos_in_album=len(in_album))
    return info


def _save(image, path):
    image.save(path, "JPEG", quality=85)


def _write_overview(folder, album, files, results, photos):
    """album.html: the cover, then the pages as open-book spreads (right to left)."""
    def page(file, number):
        label = "כריכה" if number == 0 else f"עמוד {number}"
        return f'<figure><img src="{file}"><figcaption>{label}</figcaption></figure>'

    pages = files[1:]
    # In a Hebrew book page 1 is on the left of the first spread, then 2|3, 4|5 …
    spreads = [[None, 1]] + [[n, n + 1] for n in range(2, len(pages) + 1, 2)]
    rows = []
    for spread in spreads:
        cells = []
        for n in spread:
            if n is None or n > len(pages):
                cells.append('<figure class="blank"></figure>')
            else:
                cells.append(page(pages[n - 1], n))
        rows.append(f'<div class="spread">{"".join(cells)}</div>')

    data = dict(photos)
    skipped = [r for r in results if r.grade == "skip"]
    reasons = {"blurry": "מטושטשת", "duplicate": "כפולה", "unusable": "לא שמישה"}
    left_out = "".join(
        f'<figure class="small">{_thumbnail(data[r.name])}'
        f'<figcaption>{html.escape(r.name)}<br>{reasons[left_out_reason(r)]}</figcaption></figure>'
        for r in skipped)
    notes = "".join(f"<p class='note'>⚠️ {html.escape(n)}</p>" for n in album.notes)
    design_name = {"classic": "קלאסי", "colorful": "צבעוני"}.get(album.design, album.design)
    (folder / "album.html").write_text(f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>אלבום</title>
<style>
 body {{ font-family: -apple-system, Arial, sans-serif; background:#ddd; margin:20px; }}
 .spread {{ display:flex; justify-content:center; gap:2px; margin:18px 0; }}
 figure {{ margin:0; text-align:center; font-size:13px; color:#555; }}
 figure img {{ width:420px; display:block; box-shadow:0 2px 6px #0004; }}
 .blank {{ width:420px; }}
 .small img {{ width:120px; }}
 .small {{ display:inline-block; margin:6px; }}
 .note {{ color:#a00; }}
</style></head><body>
<h2>אלבום: {len(pages)} עמודים · עיצוב {design_name} ·
{sum(r.grade != "skip" for r in results)} תמונות</h2>
<p>תמונת הכריכה לא חוזרת בתוך האלבום.</p>
{notes}
<div class="spread">{page(files[0], 0)}</div>
{''.join(rows)}
<h3>תמונות שלא נכנסו ({len(skipped)})</h3>
{left_out or '<p>אין</p>'}
</body></html>""", encoding="utf-8")


def _thumbnail(data):
    try:
        image = render.ImageOps.exif_transpose(render.Image.open(BytesIO(data))).convert("RGB")
        image.thumbnail((240, 240))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=75)
        return f'<img src="data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}">'
    except Exception:
        return ""


def order_photos(which):
    """The order's row and its photos, from Supabase."""
    sys.path.insert(0, str(PROJECT_DIR / "server"))
    from database import Database, DatabaseError
    from settings import read_env

    env = read_env()
    db = Database(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    try:
        if which == "latest":
            orders = db.recent_orders(1)
            order = db.get_order(orders[0]["id"]) if orders else None
        else:
            order = db.get_order(which) if len(which) == 36 else next(
                (db.get_order(o["id"]) for o in db.recent_orders(20)
                 if o["id"].startswith(which)), None)
        if not order:
            sys.exit("❌ Order not found.")
        rows = db.order_photos(order["id"])
        print(f"Order {order['id'][:8]}: downloading {len(rows)} photos…", file=sys.stderr)
        photos = [(f"photo {row['number']:03d}", db.download(row["storage_path"]))
                  for row in rows]
    except DatabaseError as error:
        sys.exit(f"❌ {error}")
    return order, photos


def _chosen_cover(order):
    """The photo the customer sent for the cover (kept in the order's notes
    as "cover_photo:N" by the bot), named like the photos from the order."""
    for note in order.get("notes") or []:
        if str(note).startswith("cover_photo:"):
            return f"photo {int(note.split(':')[1]):03d}"
    return None


def main():
    args = sys.argv[1:]
    options = {"--design": None, "--title": None, "--cover": None}
    flags = set()
    rest = []
    while args:
        arg = args.pop(0)
        if arg in options and args:
            options[arg] = args.pop(0)
        elif arg in ("--check", "--json"):
            flags.add(arg)
        else:
            rest.append(arg)

    if len(rest) == 2 and rest[0] == "--order":
        order, photos = order_photos(rest[1])
        design = options["--design"] or order.get("design") or "classic"
        title = options["--title"] if options["--title"] is not None else order.get("title")
        folder = OUTPUT_DIR / order["id"][:8]
        cover = options["--cover"] or _chosen_cover(order)
        cover_kept = "cover_kept" in (order.get("notes") or []) and not options["--cover"]
    elif len(rest) == 1 and not rest[0].startswith("--"):
        photos = photos_from_folder(rest[0])
        design = options["--design"] or "classic"
        title = options["--title"]
        folder = OUTPUT_DIR / Path(rest[0]).expanduser().name
        cover = options["--cover"]
        cover_kept = False
    else:
        sys.exit(__doc__)
    if design not in designs.DESIGNS:
        sys.exit(f"❌ Unknown design: {design}. Choose: {', '.join(designs.DESIGNS)}")

    if "--check" in flags:
        info = summary(quality.check_all(photos))
    else:
        print(f"Building a {design} album from {len(photos)} photos…", file=sys.stderr)
        try:
            info = build(photos, design, title, folder, cover, cover_kept)
        except ValueError as error:   # e.g. no usable photos
            info = dict(summary(quality.check_all(photos)), error=str(error))

    if "--json" in flags:
        print(json.dumps(info, ensure_ascii=False))
        return
    print(f"\n{info['photos']} photos: {info['used']} used, "
          f"{info['left_out']['blurry']} blurry, {info['left_out']['duplicate']} duplicates, "
          f"{info['left_out']['unusable']} unusable left out. "
          f"{info['without_hd']} look like they were sent without HD.")
    if "error" in info:
        sys.exit(f"❌ {info['error']}")
    if "pages" in info:
        print(f"✅ {info['pages']} pages + cover, design {design}.")
        for note in info["notes"]:
            print(f"⚠️ {note}")
        print(f"Open it:  open {folder / 'album.html'}")
        print(f"Customer previews ({len(info['previews'])} images):  open {folder / preview.FOLDER}")


if __name__ == "__main__":
    main()
