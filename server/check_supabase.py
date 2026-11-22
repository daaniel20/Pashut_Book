"""Check our Supabase project, and show the latest orders (tasks 0.3 and 1.3).

Run from the project folder:  python3 server/check_supabase.py
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


if __name__ == "__main__":
    main()
