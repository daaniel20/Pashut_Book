# Scalability review: where Pashut Book breaks as orders grow

*Review only, Nov 27, 2026. No code was changed. Steps: 5 → 20 → 50 → 200 albums a day, 40–100 HD photos each.*

## What was measured

A test album of **100 large photos** (4032×3024, about 4 MB each, 404 MB in all) was built with the real album tools on a 4-core cloud computer. Your Mac Mini (Apple Silicon) is probably 1.5–2× faster per core.

| Step | Time | Memory (RAM) | Uses |
|---|---|---|---|
| Photo check (`build_album.py --check`) | 21 s | 670 MB | 1 core |
| Build album + previews | 30 s | 670 MB | 1 core |
| Print PDF (40 pages, 300 DPI) | 15 s | 630 MB | 1 core |
| **6 albums built at the same time** | 52 s for all 6 | ~4 GB together | 4 cores |

Files on the Mac for one album: **117 MB** (the print PDF alone is 103 MB; pages + previews ~14 MB; the customer's preview page is ~5 MB per visit).

**What this means:** the computer power is **not** the problem. One album with 2 changes costs about 3 minutes of one core. Even 200 albums a day is about 10 core-hours, and a Mac Mini has 8–10 cores. The problems are **money for Supabase data, your own time, waiting lines, and failures nobody sees**.

Numbers used below (estimates; please check the real ones):
- One album's photos in Supabase: **~130 MB** (your measure: 1 GB ≈ 7–10 HD albums). Large photos can reach 400 MB.
- **The album tools download all the photos from Supabase again each time:** photo check + build + print PDF = 3 downloads, plus 2 more for every change. With 2 changes that is ~7 downloads, **about 0.4–0.9 GB of Supabase "egress" (data sent out) per album**.
- Supabase prices: Free = 1 GB storage, 5 GB egress a month. Pro = $25/month with 100 GB storage (then $0.021 per GB), 250 GB egress (then $0.09 per GB), 8 GB database.
- Half of the albums get paid. Supabase keeps unpaid photos 14 days and paid ones 30 days (task 3.4).

---

## 1. Top 10 risks

| # | What breaks | Breaks at | How bad | Easy fix (setting / paid plan) | Big fix (code / cloud) |
|---|---|---|---|---|---|
| 1 | **Supabase egress.** Every check, build, change and print PDF downloads all the photos again. The free 5 GB a month runs out after **about 5–12 albums**. After that Supabase slows or blocks the project. | **Before 5/day** (already at testing level). Pro covers up to ~20/day. 50/day: +$30–100 a month. 200/day: +$200–470 a month. | 🔴 High | Supabase Pro, **$25/month**. Keep the "spend cap" on, so a mistake can't bring a surprise bill. | Keep a **working copy of each order's photos on the Mac** (they already pass through the Mac when they come from WhatsApp). The album tools read from the Mac, and Supabase is only the backup. That means almost no egress and faster builds. Or move the photos to **Cloudflare R2** (no egress fees, ~$0.015 per GB a month). |
| 2 | **Supabase storage 1 GB.** About 120 albums are kept at a time at 5/day (~15 GB). | **5/day, first day** | 🔴 High | The same Pro plan ($25) holds ~100 GB, enough up to ~50/day. 200/day ≈ 600 GB ≈ +$10 a month. | Same as #1 (local copy / R2). Delete paid photos sooner once the printer confirms. |
| 3 | **Your own minutes.** Rough estimate per album: approval ~3 min, Bit request + check + "paid" ~3 min, help ~1 min, printer handoff and checking ~5 min, so **~10–12 min**. | 5/day ≈ 1 h a day. **20/day ≈ 4 h** (part-time job). **50/day ≈ 10 h: impossible alone.** | 🔴 High | Automatic card/Bit payment link (Grow / PayPlus / Cardcom: about 1–2.5% per payment, sometimes a monthly fee). That removes ~3 min. | Approve only the albums the bot flags (problems, notes), and let clean albums go on their own. The printer ships direct to the customer. |
| 4 | **WhatsApp's 24-hour window.** If you approve an album more than 24 h after the customer last wrote, the bot's next messages ("approved, send your address") **fail without a retry**. The bot only writes a line in bot.log (code 131047). | Already possible at 5/day (a weekend, Shabbat, a busy day). Common at 20/day+. | 🟠 Medium-high | Approve within the same day. Make Meta-approved "utility" message templates (task 0.4). They cost a few cents each (check Meta's price list for Israel). | Bot: when a send fails with 131047, re-send it as a template automatically. |
| 5 | **Failures nobody sees.** If the album build or check fails or times out, the customer gets **no message** and you get **no alert** (only a line in bot.log). A bot restart mid-build: the album is never built ("orders finished while the bot was off are not built automatically"). Photos waiting in the save line are lost on restart. A photo that fails 3 times is quietly left out. | Any scale, but it happens more often as orders grow (more restarts, more time-outs). | 🔴 High | A free outside uptime check (UptimeRobot or Healthchecks.io) on `https://bot.pashutbook.com/health`. It emails you or sends a push when the bot is down. | Small code: on any failure, send you a 🔧 WhatsApp and the customer "a small delay, we're on it". After a restart, rebuild orders stuck at "done" with no link sent. Send a daily 🔧 summary (orders, failures, storage). |
| 6 | **Power cut / internet cut / FileVault password.** After a power cut nothing runs until someone types the password at the Mac. Meta keeps trying to deliver messages for a while, so most messages arrive late, but customers wait hours with no answer. | Any scale. At 50/day an evening outage hits ~10 customers mid-order. | 🟠 Medium | A **UPS** (battery box, ~₪400–800 once) rides out short cuts. Plus the uptime alert from #5. | Move the bot to the cloud (task "keep it portable", principle 6). A small cloud server costs ~$10–25 a month. |
| 7 | **The shared photo-saving line.** All customers share **4 photo savers** (`PHOTO_WORKERS = 4`), and speed is set by your **home upload speed**. 5 customers sending at once = 500 photos in one line. The **cover check waits only 2 minutes** for its photo, then gives up (the cover isn't checked). **The album waits 15 minutes**, then is built **with photos missing**. | Evening peaks at **~20/day** on a slow upload line (~20 Mbps). ~50/day on fibre (100 Mbps+). | 🟠 Medium-high | Measure your upload speed (speedtest.net on the Mac). Upgrade to fibre if it's below ~50 Mbps up. Raising `PHOTO_WORKERS` to 8 helps only if the line has room. | Put the cover photo at the front of the line. Never build an album while its photos are still saving: wait, and tell the customer. A local copy (#1) also removes the Supabase upload from the waiting line. |
| 8 | **No limit on albums built at the same time.** Each build uses ~670 MB of RAM. A Friday-evening peak with 10 builds at once (plus cover checks and print PDFs) needs ~7 GB, so an 8 GB Mac slows to a crawl. | Peaks at **50–200/day** (earlier if the Mac has 8 GB). | 🟡 Medium | Check the Mac's RAM ( → About This Mac). 16 GB is comfortable until ~200/day. | Small code: a queue that builds at most 3 albums at a time. The others wait a minute, and the customer already has "being prepared". |
| 9 | **Mac disk fills with print PDFs.** 103 MB each, kept up to 30+ days. | ~50/day on a 256 GB Mac (~70 GB of albums). 200/day ≈ 280 GB: full. | 🟡 Medium | An external SSD (~₪300 for 1 TB). Check free space weekly. | Delete the print PDF as soon as the printer confirms it received it (it can be made again from layout.json). |
| 10 | **The printer's capacity.** Not chosen yet. A local lab may print ~10–30 albums a day, slows down before holidays (Rosh Hashana, Pesach), and 100 MB files must be sent one by one. | **20–50/day** | 🟠 Medium (it stops sales, not the bot) | Ask in the S.2 quotes: daily capacity, holiday capacity, how to send files (link, FTP, API), and drop-shipping to the customer. | Two printers (main + backup); later a printer with an upload API. Keep the printer step separate (principle 6, already the plan). |

**Also worth knowing (smaller):**
- **Supabase database 500 MB (free):** the order history writes ~250 rows per 100-photo album (each photo = a "message_in" + a "photo_saved" row), roughly 0.2 MB. It fills after ~2,500 albums: ~4 months at 20/day, ~7 weeks at 50/day. Pro (8 GB) solves it.
- **Meta limits are not the bottleneck.** Replies to customers inside the 24 h window have no daily limit. The "250 → 2,000 people a day" limits apply only to messages *you* start (templates). Throughput (~80 messages a second) is far above need. **Quality rating:** it drops if many people block or report the number. That happens with mass marketing messages, not with a bot people asked to use, so never send broadcasts from the bot's number. Until task 0.4 the test number reaches only 5 phones, so **no real customer can use the bot before 0.4**.
- **Abuse:** the per-phone limits exist, but there is **no total daily limit**. A viral ad or someone using many phone numbers could fill storage and egress in one evening. A simple setting "max new albums per day for everyone" (e.g. 30 at first), with a polite "we're full today, try tomorrow" message, protects the budget.
- **One thread per incoming photo.** 100 photos = 100 short-lived threads waiting their turn. That's fine up to ~200/day, but worth watching in bot.log.
- **Updating the bot during the day** (git pull + restart) cuts builds in the middle (see #5). Update at night until #5 is fixed.

---

## 2. Do these BEFORE launch (at most 5)

1. **Supabase Pro ($25/month), spend cap ON.** The free plan's 5 GB egress and 1 GB storage break within the first few days of real orders (risks 1, 2 and the database). Upgrade the day before the first strangers order.
2. **No silent failures (small code task).** If an album or check fails: a 🔧 WhatsApp to you and a "small delay" message to the customer. After a restart: rebuild orders stuck at "done" with no link sent. Don't build an album while its photos are still saving (risks 5, 7).
3. **A free uptime alert:** UptimeRobot or Healthchecks.io watching `https://bot.pashutbook.com/health`, alerting your phone/email. The Mac can't tell you it's off; something outside must (risk 5, 6).
4. **A UPS for the Mac and the router, and a speed test.** About ₪400–800 once. Write down your upload speed. Below ~20 Mbps up, expect waiting lines from ~20 albums a day (risks 6, 7).
5. **Utility templates for after approval** (part of task 0.4): "your album is approved, please send your address", "payment received". Also a personal rule: approve the same day (risk 4).

---

## 3. What to do at each step

### At 5 albums a day (launch)
- The 5 things above.
- Check weekly: Supabase **Usage** page (egress, storage, database) and the Mac's free disk space.
- Your time is ~1 hour a day. Write down the real minutes per album for 2 weeks; it decides when step 20 hurts.
- Get the printer's daily and holiday capacity in the S.2 quote.

### At 20 albums a day
- **Automatic payment link** (Grow / PayPlus / Cardcom, ~1–2.5% per payment), so you stop checking Bit by hand (saves ~1 hour a day).
- **Local working copy of photos on the Mac** (big fix #1). Without it, Supabase egress goes past Pro's 250 GB and starts costing ~$0.09 per GB. It also makes builds faster.
- **Build queue: max 3 albums at a time** + **cover photo first in the save line** (risks 7, 8).
- **Total daily album limit** setting (abuse/budget protection).
- Fibre internet if the upload is slow.
- Delete print PDFs after the printer confirms (risk 9).

### At 50 albums a day
- **You can't approve, collect and hand off 50 albums alone.** Choose one: (a) the bot approves clean albums by itself and you see only flagged ones; (b) hire help for a few hours a day; (c) the printer ships directly to customers.
- **Move the bot to the cloud** (~$10–25/month for a small server), or at least have a second machine ready. One Mac at home is now a single point of failure for ~10 orders an evening.
- **A second printer** as a backup, and a file-sending method that isn't manual (shared folder / FTP / API).
- Daily 🔧 summary message: orders, failures, storage, egress.
- Expected monthly costs at this step: Supabase ~$25–30 (with the local copy; ~$100+ without), cloud server ~$10–25, WhatsApp templates a few dollars, payment fees ~2%.

### At 200 albums a day
- This is a different business: a small team, a production contract with a printer that can do 200/day (with holiday peaks of 2–3×), and a support routine.
- The bot must run in the cloud with photos in cloud storage that doesn't charge for egress (R2), the album builds on a separate worker machine with a queue, and automatic retries for failed WhatsApp messages (templates).
- Supabase: Pro + extra storage ≈ $35–40/month if photos are kept locally/R2. If photos still go Supabase → Mac several times, egress alone would be **$200–470/month**.
- Upload volume from home (~26 GB a day of photos + ~20 GB of print PDFs) is too much for a home line in the evening. Another reason the cloud is a must by now.

---

*Sources for prices and limits (check before paying, they change):* [Supabase pricing](https://supabase.com/pricing), [Supabase egress](https://supabase.com/docs/guides/platform/manage-your-usage/egress), [WhatsApp messaging limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits), [WhatsApp pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing).
