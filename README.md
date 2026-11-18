# Pashut Book (פשוט בוק)

**A printed photo album, made entirely through WhatsApp.**

The customer sends their photos to a WhatsApp number, picks a design, approves a preview, and pays. A few days later a printed photo book arrives at their door. They don't need an app, a computer, or design skills.

> **Status:** Planning and Stage 0 (preparation). No code yet.

---

## The problem

Making a photo album today means copying hundreds of photos to a computer, learning an album editor, choosing a design, and picking a printing company. Many people, especially those who aren't comfortable with technology, never finish it. Their photos stay on the phone.

## The solution

Everything happens in WhatsApp, which everyone already knows how to use. The system designs the album automatically, and a person checks every album before it's printed.

## Who it's for

- Young parents and grandparents in Israel, usually 30 and older
- People who aren't tech-savvy and want the result without the work
- The bot speaks **Hebrew, English, Russian, and Arabic**, and answers in the customer's language

---

## How it works (customer journey)

1. The customer sends "Hi" to the business WhatsApp number.
2. The bot replies in the customer's language and briefly explains the process.
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
| ④ | Album builder | Our own code: HTML page templates converted to PDF and images | ₪0 |
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
- Exact price, and an ROI calculation to find the right business size
- How many free changes per album
- Which local printer to use, and the album size and number of pages
- Which payment company to use (later)
- Name and branding

---

## Roadmap

| Stage | What it includes |
|---|---|
| **0. Preparation** | Meta developer account and free test number, register the business (עוסק פטור), find a local printer, print one test album |
| **1. Basic bot** | The bot talks in 4 languages, offers design buttons, collects and stores photos |
| **2. Automatic album** | Quality check, layout, print PDF, watermarked previews |
| **3. First customers** | Friends and family. Payment, owner approval on WhatsApp, limited changes. |
| **4. Polish and grow** | Automatic changes, order tracking, an owner dashboard, a payment company, maybe Lupa |

**Goals:** the first friends-and-family customer next month, about 20 albums a month at the start, and about 100 a month after one year.

---

## Glossary

- **Server:** a computer that runs our program all the time (here, the Mac Mini).
- **API:** a "door" that lets two software systems talk to each other.
- **Webhook:** an automatic message from another system to ours, such as "a new WhatsApp message arrived" or "the customer paid".
- **Database:** an organized table where orders and customers are kept.
- **Template:** a ready-made page layout with empty spots for photos.
- **Cloudflare Tunnel:** a free, safe way to let the internet reach the Mac Mini without opening the home network.
