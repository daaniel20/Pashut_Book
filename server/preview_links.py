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


def create(folder, previews, pages, links_dir=LINKS_DIR, days=LINK_DAYS):
    """A new link code for this album. Older links to the same album stop working.
    previews is the list from build_album.py: [{"file": path, "pages": [2, 3]}, …]."""
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


def image_path(data, name):
    """The full path of one preview image of this album, or None."""
    if name not in {image["name"] for image in data["images"]}:
        return None
    path = Path(data["folder"]) / "preview" / name
    return path if path.is_file() else None


def page_html(code, data, t):
    """The album page the customer sees: all the preview images, one under the other.
    The page labels ("עמוד 5") are drawn in the images themselves (album/preview.py)."""
    images = "\n".join(
        f'<figure><img src="/album/{code}/{html.escape(image["name"])}" alt="" '
        f'loading="lazy" draggable="false"></figure>'
        for image in data["images"])
    return _PAGE.format(title=html.escape(t["preview_page_title"]),
                        note=html.escape(t["preview_page_note"].format(pages=data["pages"])),
                        images=images)


def expired_html(t):
    return _PAGE.format(title=html.escape(t["preview_page_title"]),
                        note=html.escape(t["preview_link_expired"]), images="")


_PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<style>
 body {{ margin:0; padding:16px 10px 40px; background:#eee; color:#333;
        font-family:-apple-system, Arial, sans-serif; text-align:center; }}
 h1 {{ font-size:22px; margin:6px 0; }}
 p {{ font-size:16px; margin:0 auto 18px; max-width:600px; line-height:1.4; white-space:pre-line; }}
 figure {{ margin:0 auto 22px; max-width:900px; }}
 img {{ width:100%; display:block; box-shadow:0 2px 6px #0003;
       -webkit-user-select:none; user-select:none; -webkit-touch-callout:none; }}
</style></head>
<body oncontextmenu="return false">
<h1>📖 {title}</h1>
<p>{note}</p>
{images}
</body></html>
"""
