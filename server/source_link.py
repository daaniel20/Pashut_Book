"""Make a WhatsApp link with a source code (task 3.3b).

A wa.me link opens WhatsApp with a ready-made first message to the bot. We add
a short code at the end ("#101"), so the bot records where the customer came
from (the "source" event). The customer only taps Send.

Run from the project folder:
    python3 server/source_link.py 101
    python3 server/source_link.py 501 050-1234567     (another bot number)

The bot's number comes from BOT_PHONE in .env, or the second word.
Built-in Python only.
"""

import sys
from urllib.parse import quote

from behaviour import CODE, phone_number
from settings import read_env

# The ready-made first message. The code is added at the end.
FIRST_MESSAGE = "שלום! אשמח להכין אלבום תמונות"
# Invisible marks around the code ("left-to-right isolate"), so in the Hebrew
# line it shows as "#101", not "101#" (owner's phone test, Nov 26, 2026).
LTR_START, LTR_END = "\u2066", "\u2069"


def make_link(number, code, text=FIRST_MESSAGE):
    return f"https://wa.me/{number}?text=" + quote(f"{text} {LTR_START}#{code}{LTR_END}")


def main():
    if len(sys.argv) < 2:
        sys.exit("Write a code, e.g.:  python3 server/source_link.py 101")
    code = sys.argv[1].lstrip("#").lower()
    if not CODE.fullmatch(code):
        sys.exit("❌ The code must be a number of 3-6 digits (e.g. 101), or 2-20 English "
                 "letters, digits, - or _ starting with a letter (e.g. fb1).")
    number = phone_number(sys.argv[2] if len(sys.argv) > 2 else read_env().get("BOT_PHONE"))
    if not number:
        sys.exit("❌ Which number? Add BOT_PHONE=050… to .env, or write it after the code.")
    print(make_link(number, code))


if __name__ == "__main__":
    main()
