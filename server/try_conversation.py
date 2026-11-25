"""Try the customer conversation in the Terminal, without WhatsApp.

Run:   python3 server/try_conversation.py

Type like a customer. Special commands:
  1, 2, 3     tap that button (from the bot's last message)
  /photo      send one photo        /photo 30   send 30 photos
  /photo small   a cover photo that is too small (without HD)
  /photo blurry  a blurry cover photo
  /video      send a video
  /previews   the album is built and its preview link was sent (task 2.4)
  /approve    the owner approves the album (then the address, task 3.2)
  /paid       the owner taps "payment received"
  (When the bot asks for a photo's number, a typed number is the number,
  not a button.)
  /wait       a minute passes with no new photo (the bot then sends the photo
              count with the "done" button, as it does after real photos stop)
  /wait nohd  the same, but the photos came without HD (the count asks to resend)
  /quit       stop
Nothing is sent to WhatsApp and nothing is saved.
"""

import conversation
from settings import load_texts

texts = load_texts("he")
# What the cover check (task 2.5) says about the cover photo; normally done in
# the background by the album tools. Here: good, unless "/photo small" or "/photo blurry".
COVER_RESULTS = {
    "good": {"ok": True, "problem": None, "dpi": 300, "without_hd": False},
    "small": {"ok": False, "problem": "small", "dpi": 146, "without_hd": True},
    "blurry": {"ok": False, "problem": "blurry", "dpi": 300, "without_hd": False},
}
state = conversation.new_state()
buttons = []


def show(replies):
    global buttons
    for reply in replies:
        if reply.get("video_file"):
            print("\n🎬 (video on top: the HD how-to clip)")
        print("\n🤖 " + reply["text"].replace("\n", "\n   "))
        if reply.get("list"):
            # In WhatsApp this is one button that opens a list.
            print(f"   ☰ {reply['list']['button']} (opens a list):")
            buttons = reply["list"]["rows"]
            for number, button in enumerate(buttons, start=1):
                print(f"   [{number}] {button['title']}")
        if reply.get("buttons"):
            buttons = reply["buttons"]
            for number, button in enumerate(buttons, start=1):
                print(f"   [{number}] {button['title']}")


print(__doc__)
while True:
    try:
        typed = input("\n🙂 > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if typed == "/quit":
        break
    if typed.startswith("/photo"):
        parts = typed.split()
        count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        cover = parts[1] if len(parts) > 1 and parts[1] in COVER_RESULTS else "good"
        for _ in range(count):
            show(conversation.answer(state, "photo", None, texts))
            number = conversation.checking_cover(state)
            if number:
                print(f"   (checking the cover photo: {cover})")
                show(conversation.cover_checked(state, number, COVER_RESULTS[cover], texts))
    elif typed.startswith("/wait"):
        show(conversation.photos_settled(state, texts, without_hd=typed.endswith("nohd")))
    elif typed == "/previews":
        state["notes"].append("previews_sent")
        show([conversation.after_previews(texts)])
    elif typed == "/approve":
        conversation.owner_approved(state)
        show([{"text": texts["owner_approved_customer"]}])
    elif typed == "/paid":
        conversation.owner_paid(state)
        show([{"text": texts["paid_customer"]}])
    elif typed == "/video":
        show(conversation.answer(state, "other", "video", texts))
    elif typed.isdigit() and 1 <= int(typed) <= len(buttons) and state["step"] != "photo_number":
        show(conversation.answer(state, "button", buttons[int(typed) - 1]["id"], texts))
    else:
        show(conversation.answer(state, "text", typed, texts))
    print(f"   (step: {state['step']}, photos: {state['photos']})")
