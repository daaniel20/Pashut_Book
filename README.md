# Pashut Book (פשוט בוק)

**A printed photo album, made entirely through WhatsApp.**

The customer sends their photos to a WhatsApp number, picks a design, approves a preview, and pays. A few days later a printed photo book arrives at their door. They don't need an app, a computer, or design skills.

> **Status:** Planning. Build track and sales track start together. First paying strangers by **[DATE]**.

---

## The problem

Making a photo album today means copying hundreds of photos to a computer, learning an album editor, choosing a design, and picking a printing company. Many people, especially those who aren't comfortable with technology, never finish it. Their photos stay on the phone.

## The solution

Everything happens in WhatsApp, which everyone already knows how to use. The system designs the album automatically, and a person checks every album before it's printed.

## Who it's for

- Young parents and grandparents in Israel, usually 30 and older
- People who aren't tech-savvy and want the result without the work
- Languages: **Hebrew at launch**; Russian, Arabic and English later, each together with a marketing campaign for that audience

---

## How it works (customer journey)

1. The customer sends "Hi" to the business WhatsApp number.
2. The bot replies in Hebrew (other languages later) and briefly explains the process.
3. The customer picks one of **2 designs** by tapping a button (for example "Classic" or "Colorful").
4. The bot explains how to send photos in **HD** quality.
5. The customer sends **up to 50–100 photos** (the exact limit is still to be decided).
6. The customer can add an optional cover title.
7. **Automatic step:** the system checks photo quality, removes duplicates and blurry photos, sorts by date, picks a cover, and builds the album.
8. The customer gets **small page images with a "PREVIEW" watermark**. They never get the PDF, so they can't print it elsewhere.
9. The customer approves, or asks for a **limited number of simple changes** (for example "Page 5: remove photo").
10. The customer pays with a **Bit or credit card** link and sends a shipping address.
11. **The owner checks and approves** the album.
12. The print-quality PDF goes to the printer, and the album is shipped.

---

## Marketing and sales

- **Main principle:** our advantage is marketing, service and speed, not the tool. The tool can be copied.
- **Channels to test:**
  - Family and friends WhatsApp groups
  - A paid ad test, run by a friend
  - A "gift for grandparents" offer
- **Referrals:** every album includes a QR code and a referral offer on the back cover.
- **Speed promise to test:** a preview within 24 hours of receiving the photos.
- **Seasonal calendar:** holidays, the end of the school year, after summer trips.
- **Target:** the cost to win one paying customer from ads is **at most half** of our profit per album (before ads). This rule is the single source of truth for ad spending.
  - **Profit per album (before ads) = price − printing − payment fees − packaging and other small costs.** Shipping is left out: the customer pays it, and it costs us the same amount.
  - Current estimate: ₪150 (price, not final) − ₪50 (printing, a guess until the printer quote) − ₪3.6 (payment fees, 2% of ₪180 incl. shipping) − ₪13 (packaging ₪5, AI and WhatsApp ₪3, reprint margin ₪5) = **about ₪83**. Half of that = **about ₪42**.
  - Recalculate whenever the price, printing cost or payment method changes. The [ROI calculator (Google Sheet)](https://docs.google.com/spreadsheets/d/1ZCKRQZeCI5KIRq7gG5fmPfoNe2K_A7gINmlTygY1NUw/edit) does this automatically.

---

## System overview

```
 Customer's WhatsApp
        │
        ▼
 ① WhatsApp Business Platform (official Meta API)
        │
        ▼
 ② Server ("the brain"), Python, runs on a Mac Mini at first
        │   + Claude AI: understands free text in 4 languages, helps pick photos
        │
   ┌────┼─────────────────┐
   ▼    ▼                 ▼
 ③ Supabase    ④ Album builder     ⑤ Payment
 (database +   (quality check,     (Bit request by hand at first,
  photo         layout, print PDF,   then a payment company:
  storage)      watermarked previews) Grow / PayPlus / Cardcom)
        │
        ▼
 ⑥ Owner approval, through the owner's own WhatsApp
        │
        ▼
 Printer → Shipping → Customer
```

| # | Part | Tool | Start-up cost |
|---|---|---|---|
| ① | Talking with customers | WhatsApp Business Platform (official). A free Meta test number for development. | ₪0 |
| ② | Server / logic | Python, running on the owner's Mac Mini, exposed to the internet with **Cloudflare Tunnel** | ₪0 |
| ② | AI | Claude (Anthropic) | about ₪5–30 a month |
| ③ | Data and photos | Supabase (free plan) | ₪0 |
| ④ | Album builder | Our own code: page templates as data, drawn into page images and a PDF | ₪0 |
| ⑤ | Payment | Bit request sent by hand at first, later a payment company | ₪0 at first |
| ⑥ | Owner approval | The owner's personal WhatsApp ("Approve" / "Problem" buttons) | ₪0 |

**Main rule: keep costs low at the start.** Pay for a service only when it actually slows the business down.

---

## Key decisions

| Topic | Decision |
|---|---|
| Product | A real printed photo book (not a digital-only album) |
| Design | Fully automatic, with 2 basic designs to choose from |
| Quality control | A person checks every album before printing |
| Preview | Small page images with a watermark. Never the PDF. |
| Changes | A limited number of simple changes (exact number to be decided). Done by hand at first. |
| Photos | Sent in WhatsApp using the HD option. Low-quality photos go only in small spots on a page. |
| Photo limit | 50–100 photos per album (to be decided) |
| Price | ₪100–300 per album, before shipping (to be decided) |
| Printing | A local printer at first (easy to automate). Lupa is an option later. |
| WhatsApp | Only the **official** Meta platform. Unofficial tools risk a number ban. |
| Hosting | The Mac Mini at home at first. Move to the cloud at about 30–50 albums a month. |
| Data safety | Orders and photos are stored in Supabase (cloud), not only on the Mac |
| Privacy | Customer photos (often of children) are private and deleted automatically after delivery (for example after 60 days) |

## Open questions

- Exact photo limit (50 or 100)
- Exact price. The [ROI calculator](https://docs.google.com/spreadsheets/d/1ZCKRQZeCI5KIRq7gG5fmPfoNe2K_A7gINmlTygY1NUw/edit) is built; the final price waits for the printer quote and the first 10 albums.
- How many free changes per album
- Which local printer to use, and the album size and number of pages
- Which payment company to use (later)
- Name and branding
- Whether WhatsApp HD photos print well enough at full-page size
- Whether customers can send a shared Google Photos / iCloud album link instead of choosing 50–100 photos themselves

---

## Roadmap

Two tracks run **in parallel**. Building the bot is also a learning goal, but it must not delay finding out whether people will pay.

### Build track

| Stage | What it includes |
|---|---|
| **0. Preparation** | Meta developer account and the free test number. The test number can only message **up to 5 pre-registered phone numbers** (confirmed in Meta's documentation), so a **real business number** on the WhatsApp Business Platform is needed for customers. Meta also blocks sending from a new business until it passes **Business Verification**, which needs an official business document (for example עוסק פטור). Find a local printer. Print 1 test album from WhatsApp HD photos. |
| **1. Basic bot** | **Hebrew only** at first. Design buttons. Collect and store photos. |
| **2. Automatic album** | Quality check, layout, print PDF, watermarked previews |
| **3. First customers through the bot** | Payment, owner approval on WhatsApp, limited changes |
| **4. Polish and grow** | **Only after the go/stop decision passes** (see below) |

### Sales track (runs in parallel from week 1)

**Fixed date: first paying strangers by [DATE].** If the bot isn't ready by then, those albums are made by hand.

| When | What |
|---|---|
| **Weeks 1–2** | 2 templates ready, a printer quote, a test album printed |
| **Weeks 3–6** | **10 albums:** 5 for friends and family at **full price**, and 5 for strangers from a small paid ad test (about ₪1,500) |

**Track for every album:**
- Owner minutes spent
- Number of revision requests
- Price paid
- How the customer found us

### Go / stop decision (after the 10 albums, before Stage 4)

The criteria are set **now**, not after the test. Continue only if **all** of them pass:

- [ ] At least **5 strangers** paid
- [ ] Cost per paying customer from ads: **at most half of profit per album** — about ₪42 at current estimates. Recalculate after the printer quote and final price are set.
  (Profit per album = price − printing − payment fees − packaging and other small costs. See the rule under "Marketing and sales" in README.md.)
- [ ] Owner time per album: **30 minutes or less**
- [ ] At least **1 referral or repeat order**

If not: change **one** thing (price, offer, or audience) and rerun the test once, or stop the business side. The bot stays as a learning project.

---

## Glossary

- **Server:** a computer that runs our program all the time (here, the Mac Mini).
- **API:** a "door" that lets two software systems talk to each other.
- **Webhook:** an automatic message from another system to ours, such as "a new WhatsApp message arrived" or "the customer paid".
- **Database:** an organized table where orders and customers are kept.
- **Template:** a ready-made page layout with empty spots for photos.
- **Cloudflare Tunnel:** a free, safe way to let the internet reach the Mac Mini without opening the home network.
