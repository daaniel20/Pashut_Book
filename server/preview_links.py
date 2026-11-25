"""Private links to the customer's album preview (task 2.4).

Instead of 14+ separate images in WhatsApp, the customer gets one message with
a button that opens a web page with the whole album (the same small images with
the PREVIEW mark, made by album/preview.py). The page is served by the bot on
this Mac, through the Cloudflare Tunnel: https://bot.pashutbook.com/album/<code>

Protecting the photos:
- The code in the link is long and random (like a password), so nobody can
  guess it. Only the customer gets it.
- The link stops working after LINK_DAYS days, and when the album is built
  again (the customer gets a new link then).
- Search engines are told not to list the page, and the browser is told not to
  keep copies.
- Only the preview images of that album can be opened, nothing else on the Mac.

The links are kept as small files in output/preview-links/<code>.json
(output/ is never uploaded to GitHub). Built-in Python only.
"""

import html
import json
import re
import secrets
import time
from pathlib import Path

from settings import PROJECT_DIR

LINKS_DIR = PROJECT_DIR / "output" / "preview-links"
LINK_DAYS = 30
_CODE = re.compile(r"^[A-Za-z0-9_-]{32}$")


def create(folder, previews, pages, links_dir=LINKS_DIR, days=LINK_DAYS,
           photos=None, design=None, full_pages=None, photos_on_pages=None, left_out=None):
    """A new link code for this album. Older links to the same album stop working.
    previews is the list from build_album.py: [{"file": path, "pages": [2, 3]}, …].
    photos, design, full_pages (pages with one edge-to-edge photo), photos_on_pages
    and left_out ({"blurry": 2, ...}) are shown at the top of the page."""
    links_dir.mkdir(parents=True, exist_ok=True)
    folder = str(folder)
    for old in links_dir.glob("*.json"):
        try:
            if json.loads(old.read_text(encoding="utf-8")).get("folder") == folder:
                old.unlink()
        except (OSError, ValueError):
            pass
    code = secrets.token_urlsafe(24)   # 32 letters and digits
    data = {
        "folder": folder,
        "pages": pages,
        "photos": photos,
        "design": design,
        "full_pages": full_pages,
        "photos_on_pages": photos_on_pages,
        "left_out": left_out,
        "images": [{"name": Path(p["file"]).name, "pages": p["pages"]} for p in previews],
        "expires": time.time() + days * 24 * 3600,
    }
    (links_dir / f"{code}.json").write_text(json.dumps(data), encoding="utf-8")
    return code


def find(code, links_dir=LINKS_DIR):
    """The link's details, or None if there's no such link or it has expired."""
    if not _CODE.match(code or ""):
        return None
    path = links_dir / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() > data["expires"]:
        path.unlink(missing_ok=True)
        return None
    return data


def current(folder, links_dir=LINKS_DIR):
    """The album's live link: (code, details), or (None, None). Used to show the
    owner the same page the customer got (task 3.1), without replacing it."""
    folder = str(folder)
    for path in links_dir.glob("*.json") if links_dir.exists() else []:
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("folder") != folder:
                continue
        except (OSError, ValueError):
            continue
        data = find(path.stem, links_dir)
        if data:
            return path.stem, data
    return None, None


def image_path(data, name):
    """The full path of one preview image of this album, or None."""
    if name not in {image["name"] for image in data["images"]}:
        return None
    path = Path(data["folder"]) / "preview" / name
    return path if path.is_file() else None


def page_html(code, data, t):
    """The album page the customer sees: the facts about the album in a box,
    a short note, all the preview images one under the other (each page's label,
    "עמוד 5", is drawn in the image itself, album/preview.py), and at the bottom
    what to do next. Hebrew only, aligned right (owner's feedback, Nov 24, 2026).

    All the pictures load at once (an album is only ~3-5 MB), and a picture
    that fails to arrive is asked for again, up to 4 times. Owner's test
    (Nov 24, 2026): on an iPhone some pages showed "?" (on the Mac they all
    showed): a picture that hiccups on the way through mobile internet and
    Cloudflare was never asked for again, especially with "load when scrolled
    near" (lazy loading)."""
    images = "\n".join(
        f'<figure><img src="/album/{code}/{html.escape(image["name"])}" alt="" '
        f'draggable="false" onerror="tryAgain(this)"></figure>'
        for image in data["images"])
    facts = [t["preview_info_pages"].format(pages=data["pages"])]
    if data.get("photos"):
        facts.append(t["preview_info_photos"].format(photos=data["photos"]))
    if data.get("photos_on_pages") and data["pages"]:
        average = round(data["photos_on_pages"] / data["pages"], 1)
        facts.append(t["preview_info_per_page"].format(average=f"{average:g}"))
    if data.get("full_pages"):
        facts.append(t["preview_info_full_pages"].format(count=data["full_pages"]))
    left = _left_out(data.get("left_out"), t)
    if left:
        facts.append(left)
    if data.get("design") and "design_" + data["design"] in t:
        facts.append(t["preview_info_design"].format(design=t["design_" + data["design"]]))
    info = "".join(f"<div>{html.escape(fact)}</div>" for fact in facts)
    return _PAGE.format(title=html.escape(t["preview_page_title"]),
                        info=f'<div class="info">{info}</div>',
                        note=_lines(t["preview_page_note"]), images=images,
                        end=f'<div class="end">{_lines(t["preview_page_end"])}</div>')


def _left_out(left_out, t):
    """"🔍 לא נכנסו לאלבום: 2 תמונות מטושטשות, תמונה כפולה אחת", or None."""
    parts = []
    for reason in ("blurry", "duplicate", "unusable"):
        count = (left_out or {}).get(reason, 0)
        if count:
            one, many = t["left_out_" + reason]
            parts.append(one if count == 1 else many.format(count=count))
    if not parts:
        return None
    total = sum((left_out or {}).values())
    verb = t["left_out_verb_one"] if total == 1 else t["left_out_verb_many"]
    return t["preview_info_left_out"].format(list=", ".join(parts), verb=verb)


def expired_html(t):
    return _PAGE.format(title=html.escape(t["preview_page_title"]), info="",
                        note=_lines(t["preview_link_expired"]), images="", end="")


def _lines(text):
    """Each line of the text as its own paragraph."""
    return "".join(f"<p>{html.escape(line)}</p>" for line in text.split("\n") if line.strip())


_PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<style>
 body {{ margin:0; padding:18px 12px 40px; background:#eee; color:#333;
        font-family:-apple-system, Arial, sans-serif; text-align:right; }}
 .text {{ max-width:600px; margin:0 auto; }}
 h1 {{ font-size:24px; margin:4px 0 14px; }}
 .info {{ background:#fff; border-radius:12px; padding:12px 16px; margin-bottom:16px;
          font-size:18px; line-height:1.8; box-shadow:0 1px 3px #0002; }}
 p {{ font-size:16px; margin:0 0 6px; line-height:1.5; }}
 .note {{ margin-bottom:22px; color:#555; }}
 figure {{ margin:0 auto 22px; max-width:900px; }}
 img {{ width:100%; display:block; box-shadow:0 2px 6px #0003;
       -webkit-user-select:none; user-select:none; -webkit-touch-callout:none; }}
 .end {{ max-width:600px; margin:10px auto 0; padding-top:18px; border-top:1px solid #ccc; }}
 .end p {{ font-size:18px; }}
</style></head>
<script>
 // A picture that didn't arrive: ask again after 1, 2, 3, 4 seconds.
 function tryAgain(img) {{
   var tries = Number(img.dataset.tries || 0);
   if (tries >= 4) return;
   img.dataset.tries = tries + 1;
   setTimeout(function () {{
     img.src = img.src.split("?")[0] + "?try=" + (tries + 1);
   }}, 1000 * (tries + 1));
 }}
</script>
<body oncontextmenu="return false">
<div class="text">
<h1>📖 {title}</h1>
{info}
<div class="note">{note}</div>
</div>
{images}
{end}
</body></html>
"""
