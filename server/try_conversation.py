"""Try the customer conversation in the Terminal, without WhatsApp.

Run:   python3 server/try_conversation.py

Type like a customer. Special commands:
  1, 2, 3     tap that button (from the bot's last message)
  /photo      send one photo        /photo 30   send 30 photos
  /video      send a video
  /quit       stop
Nothing is sent to WhatsApp and nothing is saved.
"""

import conversation
from settings import load_texts

texts = load_texts("he")
state = conversation.new_state()
buttons = []


def show(replies):
    global buttons
    for reply in replies:
        print("\n🤖 " + reply["text"].replace("\n", "\n   "))
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
        for _ in range(count):
            show(conversation.answer(state, "photo", None, texts))
    elif typed == "/video":
        show(conversation.answer(state, "other", "video", texts))
    elif typed.isdigit() and 1 <= int(typed) <= len(buttons):
        show(conversation.answer(state, "button", buttons[int(typed) - 1]["id"], texts))
    else:
        show(conversation.answer(state, "text", typed, texts))
    print(f"   (step: {state['step']}, photos: {state['photos']})")
