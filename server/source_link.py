"""Make a WhatsApp link with a source code (task 3.3b).

A wa.me link opens WhatsApp with a ready-made first message to the bot. We add
a short code at the end ("#fb1"), so the bot records where the customer came
from (the "source" event). The customer only taps Send.

Run from the project folder:
    python3 server/source_link.py fb1
    python3 server/source_link.py flyer 050-1234567     (another bot number)

The bot's number comes from BOT_PHONE in .env, or the second word.
Built-in Python only.
"""

import re
import sys
from urllib.parse import quote

from behaviour import phone_number
from settings import read_env

# The ready-made first message. The code is added at the end.
FIRST_MESSAGE = "שלום! אשמח להכין אלבום תמונות"


def make_link(number, code, text=FIRST_MESSAGE):
    return f"https://wa.me/{number}?text=" + quote(f"{text} #{code}")


def main():
    if len(sys.argv) < 2:
        sys.exit("Write a code, e.g.:  python3 server/source_link.py fb1")
    code = sys.argv[1].lstrip("#").lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,19}", code):
        sys.exit("❌ The code must start with a letter and have 2-20 English letters, "
                 "digits, - or _ (e.g. fb1, flyer_tlv).")
    number = phone_number(sys.argv[2] if len(sys.argv) > 2 else read_env().get("BOT_PHONE"))
    if not number:
        sys.exit("❌ Which number? Add BOT_PHONE=050… to .env, or write it after the code.")
    print(make_link(number, code))


if __name__ == "__main__":
    main()
