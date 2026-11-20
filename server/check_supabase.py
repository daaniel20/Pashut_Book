"""Check that the Mac can reach our Supabase project (task 0.3).

Run from the project folder:  python3 server/check_supabase.py
It reads SUPABASE_URL and SUPABASE_SECRET_KEY from the .env file.
It never prints the key.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def read_env(path):
    """Read simple NAME=value lines from the .env file."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def main():
    env = read_env(ENV_FILE)
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

    # Ask Supabase for the list of photo storage buckets. Needs a valid key.
    request = urllib.request.Request(
        f"{url}/storage/v1/bucket", headers={"apikey": key}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            buckets = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"❌ Supabase answered with error {error.code}. "
                 "Check that the key was copied in full.")
    except urllib.error.URLError as error:
        sys.exit(f"❌ Could not reach Supabase: {error.reason}. "
                 "Check SUPABASE_URL and the internet connection.")

    print(f"✅ Connected to Supabase. Photo buckets so far: {len(buckets)}")


if __name__ == "__main__":
    main()
