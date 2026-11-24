"""Check the customer's cover photo as soon as it arrives (task 2.5).

The bot runs this right after a customer sends their cover photo, so it can
tell them within seconds if the photo is too small or blurry for the cover.

Run from the project folder, with the project's Python (.venv):

  .venv/bin/python album/check_cover.py ~/Desktop/photo.jpg
      checks one photo file

  .venv/bin/python album/check_cover.py --order latest --photo 1
      checks photo number 1 of an order in Supabase (the bot uses this, with --json)

The answer:
  ok          True if the photo is fine for the cover
  problem     "small" (prints under 150 DPI when cut to the cover's square shape:
              the album shows it smaller), "low" (150-179 DPI, printer.COVER_ASK_DPI:
              fine full size, a bit less sharp, e.g. a 3:2 photo without HD),
              or "blurry", or none
  dpi         how sharp it would print on the cover (dots per inch; 300 is perfect)
  without_hd  True if it looks like it was sent without HD (exactly 2048 px)
"""

import json
import sys

import layout
import printer
import quality
from check_photos import PROJECT_DIR


def check(name, data):
    """Check one photo (its bytes) for the cover."""
    result = quality.check_photo(name, data)
    if "unreadable" in result.problems:
        # Can't open it here; let the album decide later rather than worry the customer.
        return {"ok": True, "problem": None, "dpi": 0, "without_hd": False}
    dpi = layout.cover_dpi(result)
    problem = None
    if "too_small" in result.problems or dpi < printer.LOW_DPI:
        problem = "small"
    elif "blurry" in result.problems:
        problem = "blurry"
    elif dpi < printer.COVER_ASK_DPI:
        problem = "low"
    return {"ok": problem is None, "problem": problem, "dpi": dpi,
            "without_hd": result.long_side == quality.WITHOUT_HD_PIXELS}


def order_photo(which, number):
    """One photo of an order, from Supabase: (name, bytes)."""
    sys.path.insert(0, str(PROJECT_DIR / "server"))
    from database import Database, DatabaseError
    from settings import read_env

    env = read_env()
    db = Database(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    try:
        if which == "latest":
            which = db.recent_orders(1)[0]["id"]
        row = next((r for r in db.order_photos(which) if r["number"] == number), None)
        if not row:
            sys.exit(f"❌ Photo {number} of order {which[:8]} is not saved.")
        return f"photo {number:03d}", db.download(row["storage_path"])
    except (DatabaseError, IndexError) as error:
        sys.exit(f"❌ {error or 'No orders yet.'}")


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) == 4 and args[0] == "--order" and args[2] == "--photo":
        name, data = order_photo(args[1], int(args[3]))
    elif len(args) == 1 and not args[0].startswith("--"):
        with open(args[0], "rb") as file:
            name, data = args[0], file.read()
    else:
        sys.exit(__doc__)
    result = check(name, data)
    if as_json:
        print(json.dumps(result))
    elif result["ok"]:
        print(f"✅ Fine for the cover ({result['dpi']} DPI).")
    else:
        hd = " It looks like it was sent without HD." if result["without_hd"] else ""
        print(f"⚠️ {result['problem']} ({result['dpi']} DPI on the cover).{hd}")


if __name__ == "__main__":
    main()
