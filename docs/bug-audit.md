# Bug audit (Nov 27, 2026)

A review of the bot and the album builder, looking for bugs that could break a
customer's order or crash the bot. **No code was changed.** Fix them one by
one, each in a new conversation.

Files read: `server/` bot, conversation, orders, album_job, cover_check,
owner_approval, cleanup, database, whatsapp, history; `album/` build_album,
layout, render, print_pdf, preview, quality, check_cover; `requirements.txt`.

Left out on purpose (already known, see the scalability review): a failed
album build tells no one, a restart loses albums being built, and an album can
be built with photos missing when saving is slow.

"Proven" means I ran it here (with made-up photos and the project's own
pretend Supabase from `tests/test_orders.py`) and saw it happen. "From the
code" means I followed the code carefully but couldn't run it without real
WhatsApp.

---

## 1. Owner approves while the customer is changing the album: the change is lost

- **Severity:** High (proven)
- **Where:** `server/orders.py` `owner_decided()`; `server/conversation.py` `owner_approved()`
- **What happens:** The customer taps "😍 אהבתי!", so the owner gets an
  approval request. The customer then has second thoughts: "✏️ לשנות משהו" →
  "change the title". The owner's request is still valid, because the
  request is only cancelled once a change is *finished*. The owner taps
  "✅ לאשר". The customer jumps straight to "what's your name for shipping?".
  The new title they then type is saved as their **shipping name**
  (tested: name = "הטיול לאילת 2026", title still empty). The album goes to
  print without the change they asked for. Same thing mid photo-replace.
- **How to fix:** When a change *starts* (not only when it ends), cancel the
  owner's request. Or: `owner_decided` only approves when the customer is at
  step "done" with no change in progress; otherwise it tells the owner "the
  customer is changing the album".

## 2. The owner can't approve or mark "paid" an album once the customer starts another one

- **Severity:** High (proven)
- **Where:** `server/orders.py` `_current()` (used by `owner_decided`, `owner_paid`, `owner_token`)
- **What happens:** The owner's buttons only work on the customer's *newest*
  album. Example: a grandmother gets to "waiting for payment" for album 1, then
  types "אלבום חדש" to make a second album for another grandchild (allowed: a
  finished album is kept). The owner gets the Bit money and taps
  "💰 התקבל תשלום": the bot answers "old request" (tested). Album 1 stays
  "approved, not paid" forever, and "אישורים" quietly skips it. Combined with
  bug 3, its photos are then deleted.
- **How to fix:** Let the owner's actions work on any order by its ID. Load
  that order from Supabase when it isn't the customer's current one, instead
  of requiring it to be the newest.

## 3. Cleanup deletes approved albums that are waiting for payment

- **Severity:** High (proven)
- **Where:** `server/cleanup.py` `reason()`
- **What happens:** Everything that isn't "paid" or "cancelled" counts as
  "unpaid" and is deleted 14 days after the last change. That includes albums
  **you already approved** that are waiting for the Bit payment (status
  "approved"). If you forget to tap "paid", or the customer pays on day 15, or
  bug 2 blocked the button, the photos and print files are gone and the order
  is closed. Tested: an "approved" album 15 days old → "unpaid" → deleted.
- **How to fix:** Never delete "approved" albums by itself. Instead, a few days
  before the deadline, remind the owner (in the "אישורים" list). Or give them a
  much longer limit (e.g. 60 days).

## 4. A broken replacement photo blocks the album for good

- **Severity:** High (proven)
- **Where:** `album/layout.py` `change_photos()` → `album/render.py` `PhotoBox.open()`
- **What happens:** "Replace photo 5" uses the new photo *even if it can't be
  opened* (a damaged file, or an image type Pillow can't read sent "as a
  file", e.g. SVG). Drawing the page then crashes (tested:
  `UnidentifiedImageError`). The note "replaced:5:46" stays in the order, so
  **every** later rebuild crashes too, and the customer has no way to undo a
  replacement. Nobody is told (see the known issue). The album is stuck.
- **How to fix:** If the replacement photo is "unreadable" (or too small),
  ignore that replacement and tell the customer "this photo can't be used,
  please send another". Also catch drawing errors per photo so one bad file
  can't stop the whole album.

## 5. A tiny or very thin picture crashes the photo check

- **Severity:** Medium (proven)
- **Where:** `album/quality.py` `_sharpness()`
- **What happens:** A picture smaller than 4 pixels, or a very long thin strip
  (e.g. 3000×3, or 3000×10 after shrinking), crashes the sharpness check
  (tested: `ValueError: Coordinate 'right' is less than 'left'`). One such
  picture among 100 stops the whole album: the check fails, the album is never
  built. Also crashes the cover check. Rare (must be sent "as a file"), but
  the damage is total.
- **How to fix:** In `check_photo`, mark anything below `MIN_PIXELS` as
  "too_small" *before* measuring sharpness, and skip the measuring. Also put
  the measuring inside the same "can't open → skip" safety net.

## 6. Photos sent after the summary bypass the "5 times adding photos" limit

- **Severity:** Medium (proven)
- **Where:** `server/conversation.py` `_on_photo()` (step "done") and `photos_settled()`
- **What happens:** The limit only counts the "📸 להוסיף תמונות" button.
  Simply sending photos after the summary (without the button) rebuilds the
  album every time they stop for a minute, with no count. Tested: 8 single
  photos → 8 full rebuilds, limit counter still 0. Someone could keep the Mac
  busy rebuilding up to the 100-photo cap (CLAUDE.md rule 11).
- **How to fix:** Count each batch of late photos as one "add photos" change
  (`used_photos`). When the limit is reached, keep the photos quietly but say
  the limit message once and don't rebuild.

## 7. The owner's "type your message" mode never ends

- **Severity:** Medium (from the code)
- **Where:** `server/owner_approval.py` `handles()` / `_writing`
- **What happens:** After you tap "⚠️ יש בעיה" or "💬 לענות", the bot waits
  for your next text and sends it to the customer as a message from the team.
  There is no time limit. If you tap it and get distracted, your next text
  *hours later* (e.g. "אישורים", or a message while testing as a customer
  from your own phone) is sent to that customer word for word.
- **How to fix:** Forget the waiting mode after ~10 minutes, and don't treat
  "אישורים" as a message. Optional: show "send to customer …123?" with a
  confirm button.

## 8. Resending in HD while the old photos are still being saved

- **Severity:** Medium (from the code)
- **Where:** `server/orders.py` `_answer()` (the `resend_photos` part) and `save_photo()`
- **What happens:** When the first HD photo arrives, the old photos are
  deleted right away. But old photos still waiting in the saving queue are
  saved *after* that deletion, with their old numbers. Result: old non-HD
  photos come back into the album, or an old photo writes over a new HD photo
  with the same number (same file name, overwrite is on). Most likely when
  many photos were sent and the internet is slow (the bot asks about HD after
  waiting only 20 seconds for saving).
- **How to fix:** Before deleting, wait for that order's saves to finish (the
  bot already has `wait_for_photos`), or give each round of photos its own
  folder/name so old saves can't collide with new ones.

## 9. Photos may be numbered in a different order than they were sent

- **Severity:** Medium (from the code)
- **Where:** `server/bot.py` `do_POST()` / `handle_notice()`
- **What happens:** Each WhatsApp notice is handled in its own thread, and
  they then wait for the customer's lock. The lock doesn't keep "first come,
  first served", and Meta doesn't promise order either. So when 50 photos
  arrive within seconds, photo numbers can be shuffled. WhatsApp removes the
  date taken, so the album's order *is* the number order: photos from the
  same moment can end up apart. Bot replies can also arrive out of order.
- **How to fix:** Use the `timestamp` that comes with each message to sort
  photos (number them by it), or handle each customer's messages in one queue
  in arrival order.

## 10. Emoji reactions (❤️ on a bot message) get confusing answers

- **Severity:** Medium (proven)
- **Where:** `server/conversation.py` `read_message()` / `answer()`
- **What happens:** Grandparents often react with ❤️ or 👍. WhatsApp sends a
  reaction as a message, and the bot treats it like a wrong answer. Tested:
  at the design step → "choose a design with the buttons"; while sending
  photos → "you can only send photos 🙂"; at the title question → "we got 0
  photos 👍, want a title?". Not a crash, but confusing for the audience.
- **How to fix:** Ignore messages of type "reaction" (answer nothing), like
  "unsupported" already is.

## 11. Very large phone photos (200 MP) are silently left out

- **Severity:** Medium (proven)
- **Where:** `album/quality.py` `check_photo()` (Pillow's "too many pixels" guard)
- **What happens:** Pillow refuses pictures above ~179 million pixels as a
  safety measure. A 200 MP photo (some Samsung phones), sent "as a file", is
  marked "can't open" and left out as "unusable" (tested). As a cover photo
  it's worse: the cover check says "OK" (it doesn't worry the customer about
  unreadable photos), then the album quietly uses a different cover.
- **How to fix:** Raise Pillow's limit to a safe value for photos (e.g. 250
  million pixels) and shrink very big photos early. In the cover check,
  "unreadable" should ask for another photo instead of saying OK.

## 12. Double-tapping "yes, start over" can use up the day's 3 new albums

- **Severity:** Medium (proven)
- **Where:** `server/conversation.py` `_restart()`
- **What happens:** The first tap starts the new album. The second tap
  (a double tap, or a slow phone) asks "are you sure you want to start over?"
  again, about the brand-new empty album. Tapping yes again opens another
  empty album, which counts toward the 3-a-day limit. A shaky grandparent
  could lock themselves out for the day.
- **How to fix:** Ignore "yes, start over" when there was no question waiting
  (no `confirm_restart` note): just repeat the current question.

## 13. Some limits are per album, not per customer

- **Severity:** Medium (from the code)
- **Where:** `server/conversation.py` `_to_owner()`, `_help()`; `_answer()` (title step)
- **What happens:**
  - "3 messages to the owner a day" and "עזרה once a day" are stored in the
    album's notes, so they reset with each new album. With 3 albums a day a
    customer can send 9 messages + 3 help requests a day.
  - At the title step (when changing the title), typing "📸 להוסיף תמונות"
    goes to adding photos, but it's counted as a *title* change, so adding
    photos can continue after its own limit is used up.
- **How to fix:** Count owner messages by phone number (e.g. from the order
  history, or a small in-memory counter per phone). Count the add-photos
  path as "photos" whichever step it came from.

---

## Checked and fine (no bug found)

- **Sideways phone photos (EXIF rotation):** turned the right way up in the
  photo check, the pages, the print PDF size check and the previews (tested).
- **HEIC, WebP, CMYK JPEG, 16-bit PNG, see-through PNG:** all open and check
  fine (tested). A broken or non-image file inside the album is skipped as
  "unusable" without a crash (tested), except in bugs 4 and 5.
- **No faces found:** the cropping works without faces; I found no
  division by zero in the cropping math (unreadable photos have size 0, but
  every place that divides checks for it first).
- **Memory:** 100 HD photos (577 MB of files) → 40-page album in 39 s, peak
  ~0.9 GB; print PDF in 18 s, peak ~1 GB, 183 MB file. Fine for one album at
  a time; several customers finishing at once each add ~1 GB.
- **50+ photos at once:** each photo gets its own number under the
  customer's lock, so counts are right and files don't overwrite each other
  (except bug 8). Meta sending the same message twice is caught.
- **Double taps** on "אהבתי", "address OK", "✅ לאשר", "💰 paid", change
  buttons: handled (second tap does nothing harmful).
- **Stickers, videos, voice notes, documents** (non-image): answered once or
  ignored, never counted as photos. GIFs arrive as videos.
- **Customer back after days:** the step is reloaded from Supabase; an
  expired album starts a new one with an explanation.
- **Photos left in storage:** cancelled and abandoned albums are cleaned by
  `cleanup.py`, which also finds files whose row was lost (except bug 3,
  which deletes too much, not too little).
