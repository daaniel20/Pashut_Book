"""Check our Supabase project, and show the latest orders (tasks 0.3 and 1.3).

Run from the project folder:  python3 server/check_supabase.py
Add --history to also see the newest order's history (task 3.3), step by step.
Add --funnel to see how many orders reached each stage (task 3.3b).
It reads SUPABASE_URL and SUPABASE_SECRET_KEY from the .env file.
It never prints the key, and shows only the last 3 digits of phone numbers.
"""

import sys

from database import Database, DatabaseError
from settings import ENV_FILE, read_env


def main():
    env = read_env()
    url = env.get("SUPABASE_URL", "").rstrip("/")
    key = env.get("SUPABASE_SECRET_KEY", "")

    if not ENV_FILE.exists():
        sys.exit(f"❌ No .env file at {ENV_FILE}")
    if not url:
        sys.exit("❌ SUPABASE_URL is empty in .env")
    if not key:
        sys.exit("❌ SUPABASE_SECRET_KEY is empty in .env")
    if not key.startswith("sb_secret_"):
        sys.exit("❌ SUPABASE_SECRET_KEY should start with sb_secret_ "
                 "(did you copy the publishable key by mistake?)")

    db = Database(url, key, timeout=15)
    try:
        bucket = db.bucket()
        orders = db.recent_orders(5)
    except DatabaseError as error:
        sys.exit(f"❌ {error}\n   Check the key (copied in full?) and the internet connection.")

    print("✅ Connected to Supabase.")
    if bucket.get("public"):
        print("⚠️  The photos bucket is PUBLIC. Make it private in the Supabase dashboard!")
    else:
        print("✅ The photos bucket is private.")

    if not orders:
        print("No orders yet.")
        return
    print("\nLatest orders (newest first):")
    for order in orders:
        saved = order["photos"][0]["count"] if order.get("photos") else 0
        mark = "✅" if saved == order["photo_count"] else "⏳"
        print(f"  {order['created_at'][:16].replace('T', ' ')}  …{order['phone'][-3:]}  "
              f"{order['status']:<10}  photos: {order['photo_count']} counted, "
              f"{saved} saved {mark}")
    print("\n(⏳ = some photos are still uploading, or failed. Check the log.)")
    if "--history" in sys.argv:
        show_history(db, orders[0]["id"])
    if "--funnel" in sys.argv:
        show_funnel(db)


def show_funnel(db):
    """How many orders reached each stage, customers and tests apart (task 3.3b)."""
    try:
        rows = db.funnel()
    except DatabaseError as error:
        sys.exit(f"❌ {error}\n   Did you run supabase/3.3b-behaviour-data.sql? "
                 "See docs/setup/3.3b-behaviour-data.md")
    for who in ("customers", "tests"):
        mine = [row for row in rows if row["who"] == who]
        if not mine:
            continue
        print(f"\nFunnel ({who}):")
        for row in mine:
            previous = row["percent_of_previous"]
            print(f"  {row['stage_no']:>2}. {row['stage']:<17} {row['orders']:>4}"
                  + (f"   ({previous}% of the stage before)" if previous is not None else ""))


def show_history(db, order_id):
    """The order's history (task 3.3): what happened, when, numbers only."""
    try:
        rows = db.order_events(order_id)
    except DatabaseError as error:
        sys.exit(f"❌ {error}\n   Did you run supabase/3.3-order-history.sql? "
                 "See docs/setup/3.3-order-history.md")
    print(f"\nHistory of the newest order ({order_id[:8]}), {len(rows)} moments:")
    for row in rows:
        minutes, seconds = divmod(row["seconds_from_start"] or 0, 60)
        number = "" if row["count"] is None else f" {row['count']}"
        detail = "" if row["detail"] is None else f" {row['detail']}"
        print(f"  +{minutes:>3}:{seconds:02d}  {row['event']}{detail}{number}"
              f"   (step {row['step'] or '-'}, {row['photos'] or 0} photos)")
    if not rows:
        print("  (nothing yet: the history starts with orders made after task 3.3)")


if __name__ == "__main__":
    main()
