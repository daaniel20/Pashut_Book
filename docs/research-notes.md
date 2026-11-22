# Research notes

Ideas and lessons from other projects. **These are reference notes, not decisions.** They don't change the roadmap by themselves. When a task touches one of these topics, read the relevant note, then decide.

---

## Rega: AI Album Maker (Tamir Gur), read Nov 22, 2026

- **What it is:** a free add-on ("skill") for Claude that runs on a personal computer. It turns a folder of photos into a print-ready photo book PDF. It sorts the photos, finds days and places, picks the best frame of each moment, lays out the pages in one of 15 styles (Hebrew right-to-left or English), and checks every page. It doesn't print or pay: the user orders on the printer's site (the author uses Prodigi).
- **Where:** https://github.com/tamirgur/rega-album-maker (version 1.0.2, Beta). It was announced in a LinkedIn post: 1,300 photos and videos from a 15-day Iceland trip became a 72-page album, printed and shipped to Israel for under ₪100.
- **License:** MIT. We may use and change the code for free, including for a business, **as long as we keep its license notice** (copyright Tamir Gur) in any copied part. Its fonts use the SIL Open Font License (like ours).

### 1. What it means for the business

- **It confirms principle 9 (our advantage is service, not the tool).** A tech-savvy person can now make a book for under ₪100 on their own. Our customers won't install Python and order from an overseas printer. We sell: everything in WhatsApp, a human check, and a book at the door.
- **Price anchor:** a DIY book costs under ₪100 including shipping. Our ₪100–300 price must be justified by service and convenience. Keep this in mind for S.1 (price) and the ROI sheet.

### 2. Code we might reuse (decide per task, keep the license notice)

| Their file | What it does | Our related task |
|---|---|---|
| `scripts/scan.py` | Duplicates, blur, screenshots, tiny images, dates from many sources | 2.1 (done; compare if problems appear) |
| `scripts/faces.py` + `assets/models/face_detection_yunet_2023mar.onnx` | Finds where faces are (on the computer, no one is identified) | **2.2: avoid cutting faces when cropping** |
| `scripts/layout.py` | Page layout with rules: no cut faces, nothing at the fold, exact page count | 2.2 |
| `scripts/render.py` | HTML pages → PDF (with Chrome), bleed, left-binding mirror for Hebrew | 2.3 (print PDF) |
| `scripts/check.py` | Final check of the PDF: page size, count, resolution, QR codes scan | 2.3 / owner approval |
| `scripts/clips.py`, `references/video.md` | Video clips and QR codes | Stage 4 idea |
| `assets/printers/prodigi.json` | Prodigi products, sizes, page ranges, file rules | S.2 (printer comparison) |

**Caveat:** it's built as a conversation on a personal computer, not as a server bot, and it's a Beta. Take pieces, not the whole thing.

### 3. Lessons that match what we already found

- **WhatsApp removes the date and location** from photos; the file name only shows the day it was received. We confirmed this ourselves in 2.1 (57 photos: no date, no GPS). So: keep the order the customer sent them in, and never print a date or place we aren't sure of.
- **Tiny images can't be printed:** they treat anything under 600 px as unusable. Ours: under 800 px is too small (2.1).
- **Even page count** is always required by printers (we already do this).

### 4. Rules worth adopting

- **Never cut people.** A photo with people keeps its own shape, with whole heads and feet. Only photos with no people (landscapes, food, signs) may be cropped to fill a spot. *Today our `album/render.py` crops "a bit above the middle" to keep heads. Face detection would make this safer (task 2.2 or later).*
- **Ask the customer one question:** "Who must always look their best?" Then use that person's best frame in each moment.
- **One frame per moment:** from a burst of similar shots, keep the best one (eyes open, natural smile, straight horizon).
- **Leave out** screenshots, receipts or documents with personal data, medical scenes, nudity, anything embarrassing.
- **Never invent facts.** Titles are 1–3 plain words (a place, an event). No puns or clichés: printed, they sound silly.
- **Few type sizes and one accent color.** No pages of text alone.

### 5. Print quality numbers

- **Resolution:** 300 DPI at the printed size is ideal, 200+ is fine, 150–199 shows on close look, below 150 don't use.
  For a 20 cm page at 200 DPI, a full-page photo needs about 1,600 px. A non-HD WhatsApp photo (2048 px) is enough for a full 20 cm page at about 260 DPI; HD (~5000 px) is plenty.
- **Safe area:** keep text and faces 10 mm from the edge, 15 mm on the binding side.
- **Color:** paper prints darker and less saturated than a screen. Avoid very dark photos and very deep page colors.
- **QR codes:** at least 18 mm wide, with a white margin. Keep the square corner markers (rounded ones failed to scan in print). Test with two phones. Never print a QR code to a placeholder link.

### 6. Prodigi: a third printing option (besides a local printer and Lupa)

- Ships worldwide, **Israel included**, and takes a ready PDF. It has an API.
- Example price seen in October 2026: about **$25** for a 74-page, 21×21 cm hardcover shipped to Israel, **before shipping**. Prices change: the order summary on their site is the only exact price.
- Production about **5 working days**, plus international shipping. That's slower than a local printer.
- File: one PDF, page 1 = front cover, last page = back cover, exact trim size, no bleed, 300 DPI, RGB, even page count.
- **It binds on the left only.** A Hebrew book must be uploaded "mirrored" (back cover first, pages in reverse) so it opens from the right.
- **The spine can't take Hebrew** (English, numbers, or color only). Under 40 pages, color only.
- Use it as a **price benchmark** when local printers reply (S.2).

### 7. Ideas to keep for later (not planned)

- **QR codes to short video clips** inside the album, maybe as a paid add-on.
- **Clear progress messages** for the customer: "Stage 3 of 10 · what's happening · what I need from you · what's next."
- **A one-line privacy message in Hebrew** at the start, to build trust. Their wording:
  "התמונות נשארות במחשב שלך. אני רואה תמונות ממוזערות קטנות שלהן…" (we'd need our own version, because our photos are stored in Supabase).
- **Route maps and "boarding pass" elements** from real facts. These need GPS and dates, which WhatsApp photos don't have, so they would only work if the customer tells us the facts.
