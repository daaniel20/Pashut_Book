# Event dictionary

Every row in the Supabase table `order_events` is one moment of one order. This page says what each **event** name means. Use it when you read the data or build a dashboard later.

Rules for every row (CLAUDE.md rules 5 and 10): numbers and short codes only. **Never** photos, message texts, names, addresses or phone numbers.

## The columns of every row

| Column | What it holds |
|---|---|
| `order_id` | Which order (album). `order_code` in the views = its first 8 characters, as in the bot's log. |
| `event` | What happened (the names below). |
| `step` | The conversation step at that moment (for `message_in`: the step **before** the message). |
| `photos` | How many photos the order had then. |
| `count` | The event's main number (a photo number, pages, seconds, scroll %…). |
| `detail` | A short code (the new step, a message name, "phone", "small"…). |
| `info` | More numbers, as JSON (e.g. `{"seconds": 41}`). |
| `customer` | Anonymous customer key: the phone number scrambled with a secret. Same phone = same key, but it can't be turned back into the number. Empty on rows from before task 3.3b. |
| `test` | `true` for the owner's and family's test phones (`OWNER_PHONE`, `TEST_PHONES` in `.env`). Everything before task 3.3b is marked `true`. |
| `version` | The bot's version: the date of the code's last change and its git commit, e.g. `2026-11-26.e83a816`. Compare before / after a change. |
| `created_at` | When it happened. |

## Where the customer came from (task 3.3b)

| Event | Meaning |
|---|---|
| `source` | Where the customer came from. `detail` = the code: from `#code` in the ready-made first message of one of our wa.me links (a 3-digit number whose first digit is the channel, e.g. `101` = Facebook post 1, `204` = WhatsApp group 4; the list is in guide 3.3b, step 5), or `ad` / `post` for a click on a Meta "click to WhatsApp" ad. `info`: `ad_id`, `type`, `media`, `from_ad` (Meta ads only); `carried: true` = the code came with an earlier message and the customer then started a new album within a day. |

## Messages (task 3.3b)

| Event | Meaning |
|---|---|
| `message_in` | The customer sent something. `detail` = `text` / `button` / `photo` / `other`. `info`: `expected` (what the bot was waiting for: `button`, `text`, `photo`, `any`), `changed` (did it change anything?), `confused` (typed text where a button was expected, and nothing changed), `replies` (names of the bot's answers), `button` (the button's code), `letters` (a text's length only), `type` (for `other`: video, sticker, audio…), `new_order` (it started a new album). |
| `message_out` | The bot sent a message. `detail` = its name in `server/texts/he.json` (e.g. `photos_count`, `welcome`), or `other` / `image`. `info.kind` = text / buttons / list / link / video / image. The owner's own 🔧 messages are not recorded. |
| `message_delivered` | WhatsApp says that message reached the phone. `detail` = its name; `info.seconds` = since sending. |
| `message_read` | The customer opened it (only if they didn't turn off read receipts). `info.seconds` = from sending to reading. |
| `message_failed` | WhatsApp couldn't deliver it. `info.code` = WhatsApp's error code (131047 = 24-hour window closed). |

Reports for messages sent before a bot restart are not recorded (the bot remembers its messages in memory only).

## The album page (task 3.3b)

| Event | Meaning |
|---|---|
| `album_opened` | The preview page was opened. `detail` = `phone` / `tablet` / `computer`, or `owner` (the owner's own link, which ends in `?o=1`). `info.device` = a random code kept in that browser, to count devices. |
| `album_seen` | The page was left or hidden. `count` = how far down it was scrolled (%). `info`: `seconds` on the page, `images_seen` / `images` (pictures reached of all). |

## The order's steps and notes (task 3.3, automatic)

Every save of an order records:
- `step`: a new conversation step. `detail` = the new step, `info.from` = the old one. The steps are listed at the top of `server/conversation.py`.
- one row per **new note**, named after the note. `count` = the note's number, `detail` = its text part.

| Note event | Meaning |
|---|---|
| `photo_before_design` | Photos were sent before choosing a design. |
| `cover_check` | The cover photo (`count` = its number) is being checked. |
| `cover_problem` | The cover check found a problem: `detail` = small / small_hd / low / low_hd / blurry / shape. |
| `cover_kept` | The customer kept a cover photo with a problem. |
| `cover_photo` | The cover photo was accepted (`count` = its number). |
| `counted` | "We got N photos" was sent (`count` = N). |
| `few_told`, `few_photos_ok` | Told "only a few photos"; the customer chose to continue anyway. |
| `done_waiting` | "Done" was tapped while photos were still arriving. |
| `video`, `video_untold` | A video was sent (videos don't go into the album). |
| `hd_asked`, `hd_early` | Asked to resend in HD (`hd_early` = together with the photo count). |
| `resent_from` | Photos were resent in HD, instead of `count` old ones. |
| `late_from` | Photos arrived after the summary (`count` = the count before them). |
| `confirm_restart` | "Are you sure you want to start over?" was asked. |
| `changing` | A change from the list was started: `detail` = title / design / cover / photos / photo. |
| `used_title`, `used_design`, `used_cover`, `used_photos`, `used_photo`, `used_cover_resend`, `used_ship_fix` | How many times that kind of change was made (`count`). Limit: 5 (rule 11). |
| `photo_pick` | The customer chose photo number `count` to change. |
| `removed`, `replaced` | A photo was removed (`count` = its number) / replaced (`detail` = "old:new"). |
| `previews_sent` | The preview link was sent. |
| `after_previews`, `after_done` | Messages said once per album. |
| `preview_ok` | The customer tapped "😍 אהבתי!". |
| `owner_problem`, `approved` | The owner found a problem / approved the album. |
| `owner_msgs` | A message was passed to the owner (`count` = that day's number, max 3). |
| `help_wait` | The customer typed "עזרה". |
| `ship_back` | A shipping detail is being fixed. |
| `payment_wait` | The shipping details are complete; the owner was asked to send a payment request. |
| `payment_told`, `paid_told`, `photo_after_approval`, `photo_limit` | Messages said once. |
| `paid` | The owner tapped "payment received". |
| `confirmed` | The old "everything is correct" button. |

Not recorded (codes and helper marks): `owner_token`, `help_day`, `photos_at`, `editing`, `owner_check`.

## Other moments (task 3.3)

| Event | Meaning |
|---|---|
| `order_started` | A new order was opened. |
| `new_album` | The customer started over. `detail` = `cancelled` (the old one wasn't finished) or `kept`. |
| `new_album_limit` | The customer hit the "3 new albums a day" limit. |
| `photo_saved` | A photo was saved. `count` = its number; `info`: `kb`, `long_side` (pixels), `without_hd`, `tries`, `seconds`. |
| `photo_failed` | A photo couldn't be saved. `detail` = database / too_big / error. |
| `photos_arrived` | The photos stopped arriving. `info`: how many with / without HD. |
| `photos_deleted_for_hd` | Old photos were deleted because the customer resends in HD (`count` = how many). |
| `cover_checked` | The cover check's result (`detail` = ok or the problem). |
| `album_checked`, `album_check_failed` | The photos were checked before building. |
| `album_built` | The album was built. `count` = pages, `detail` = design, `info`: photos in the album, full pages, seconds… |
| `album_failed` | The album couldn't be built. |
| `previews_waiting`, `previews_not_sent` | The link waited (customer was changing something) / couldn't be sent. |
| `owner_asked` | The owner was asked to approve. `info`: print-check problem and warning counts. |
| `owner_wrote` | The owner wrote to the customer (`count` = length only). |
| `photos_deleted` | Cleanup deleted the photos (`count` = files, `detail` = unpaid / paid / cancelled). |

## Ready-made views (Supabase → Table Editor → the view → Export to CSV)

| View | One row per | What for |
|---|---|---|
| `order_history` | moment | Every moment, with seconds since the start and since the previous moment (task 3.3). |
| `order_summary` | order | The main numbers of each order (task 3.3). |
| `order_stages` | order | How far each order got (`reached_…`, `furthest_stage_no`), test mark, source, customer key, version. The base for the views below. |
| `funnel` | stage | How many orders reached each of 11 stages, for customers and tests separately, with % of the start and % of the previous stage. |
| `drop_off` | unpaid order | Where it stopped (furthest stage, last step, last event) and how many hours ago. |
| `friction` | order | Signs of difficulty: confused messages, messages that changed nothing, help, HD resends, cover problems, limits reached, failures, how fast messages are read. |
| `weekly_trends` | week × customers/tests | Orders, how many got how far, average photos, confusion, sources, versions. |
| `customers` | customer key | Orders and paid albums per customer: repeat customers. |
| `album_page_visits` | order | Page opens, devices, phone vs computer, scroll depth, longest visit. |

To leave out tests, filter `who = customers` (or `test = false`).

## Adding a new event

When a task adds a step: prefer a new **note** or **step** in `conversation.py` (recorded automatically), or call `orders.record(...)` / `orders.record_for(...)`. Then add one line here.
