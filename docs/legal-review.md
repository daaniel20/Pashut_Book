# Legal review: Pashut Book before launch (Israel)

*Written Nov 27, 2026, by Claude (an AI), reviewing the project the way an Israeli
commercial, privacy and consumer-protection lawyer would. **This is not legal
advice.** It's a map to bring to a real Israeli lawyer, so a short paid meeting
covers the right questions. Items marked ⚖️ really need a lawyer.*

What I read: CLAUDE.md, README.md, `server/pages/privacy.html`,
`server/texts/he.json` (every customer message), `server/cleanup.py`,
`server/history.py`, `server/behaviour.py`, `server/preview_links.py`.
Nothing in the code was changed.

---

## The short version

The product's design is already privacy-friendly: private storage, automatic
deletion, no photos or message texts in the statistics, watermarked previews, and the
owner checks every album. The legal gaps are mostly **paperwork and wording**, not
code:

1. **You can't legally sell to strangers before opening a business file**
   (עוסק פטור + tax registration). This blocks everything else, including Meta
   verification.
2. **The customer never sees the price, delivery time, cancellation rules or who
   the seller is** until the last step, and some of these never appear. Israeli law
   for remote sales requires them **before** the deal.
3. **There are no terms of service** and no "I agree" moment in the chat.
4. **The privacy page promises things the system doesn't do exactly**, and it
   leaves out things the law now requires (Amendment 13).
5. **Copies of customer data sit outside the deletion system**: in your personal
   WhatsApp (cover photos, addresses), its backups, and soon at the print lab.

All five are cheap to fix. The Hebrew wording to fix them is below.

---

## Tier 1: fix before the first real (stranger) customer

### 1. Open the business, register for tax, issue receipts, use a business Bit

- **Risk / law:** Selling regularly to the public is a business. You must open a
  file with VAT (מע"מ, as עוסק פטור), Income Tax (מס הכנסה) and Bituah Leumi
  **before** the first sale. A עוסק פטור must give a **receipt (קבלה)** for every
  payment. A tax invoice (חשבונית מס) is only for עוסק מורשה, so you don't need
  one. The 2026 ceiling for עוסק פטור is **₪122,833 a year** of turnover (not
  profit). At ₪180 an album, that's about 680 albums a year.
- **Bit:** a personal Bit account is for private payments between people. Taking
  business payments into it mixes business and private money. It may also break
  Bit's terms. Bit's own fees on money received changed in 2026 (0.8% above ₪25,000
  a year from people).
- **Worst case:** tax assessments and fines for unreported income; no business
  document, so no Meta Business Verification (task 0.4), so no real WhatsApp
  number.
- **Cheap fix:**
  - Open עוסק פטור online (gov.il), the same day, free.
  - Open a **separate bank account** just for the business. Not required for
    עוסק פטור, but it makes accounting and any audit easy.
  - Use a free or cheap receipts app (Green Invoice/Morning, iCount, EZcount: about
    ₪0–40 a month) that **sends the receipt by WhatsApp or email automatically**.
  - Switch to **Bit for business** (or PayBox business) once registered. Later, a
    payment company link (Grow / PayPlus / Cardcom).
  - Consider the "בעל עסק זעיר" track (a flat 30% expense deduction, no
    receipts-for-expenses bookkeeping). ⚖️ Ask an accountant (רו"ח or יועץ מס),
    not a lawyer, which track fits.

### 2. Tell customers the price, delivery time, cancellation rules and who you are, before they pay

- **Risk / law:** Consumer Protection Law, **section 14C (עסקת מכר מרחוק)**. In a
  remote sale the business must disclose, **before the deal**: the business's
  **name, ID/business number, address and contact**; the main features of the
  product; the **full price**, including shipping and any extra cost; the
  **delivery date**; and the **cancellation terms**. It must also send a
  **written confirmation (מסמך גילוי / פרטי העסקה)** no later than delivery.
  - Today the price first appears in the `payment` message, **after** the address.
  - Delivery time, business identity and cancellation rules never appear anywhere.
- **Cancellation, the key point:** normally a customer can cancel a remote purchase
  within **14 days of receiving the goods** (cancellation fee: up to 5% or ₪100,
  whichever is lower). The Cancellation Regulations (2010) list exceptions, and
  one is **goods made especially for the consumer**. A personal photo album is the
  textbook example. So:
  - **Before the file is sent to the printer:** allow free cancellation and a
    full refund. It costs you almost nothing and avoids arguments.
  - **After printing:** no cancellation "because I changed my mind" (the
    made-to-order exception), **but** a **defective** album (bad print, damage,
    different from the approved preview) is never covered by the exception. That
    is a defect, and the customer gets a reprint or a refund.
  - ⚖️ **Senior citizens (65+), people with disabilities and new immigrants** get
    an extended cancellation period (up to 4 months) in some remote sales that
    involve a conversation with the business. Your target market is grandparents
    talking to a bot. Ask a lawyer whether this applies to a WhatsApp bot, and
    whether the made-to-order exception still wins.
- **Worst case:** a consumer class action (ייצוגית) for missing disclosures,
  administrative fines from the Consumer Protection Authority, and the customer's
  right to cancel even after printing because the rules were never told.
- **Cheap fix:** two message changes (no new steps):
  - **Price in the welcome** (see item 3's wording). People decide early; telling
    the price at the end also looks like a trap.
  - **A short disclosure in the address summary** (`address_check`), with the
    confirm button as the agreement:

    ```
    📦 פרטי המשלוח:
    {details}

    📋 לפני התשלום, בקצרה:
    💰 ₪150 לאלבום + ₪30 משלוח = ₪180, כולל הכול.
    🚚 האלבום יגיע עד {days} ימי עסקים אחרי התשלום.
    ↩️ עד שהאלבום נשלח להדפסה, אפשר לבטל ולקבל את כל הכסף.
    🖨️ אחרי ההדפסה אי אפשר לבטל, כי האלבום הודפס במיוחד בשבילכם.
    🛠️ אלבום פגום או שונה ממה שאישרתם? נדפיס מחדש או נחזיר את הכסף.
    🏷️ פשוט בוק · {owner name} · עוסק פטור {number} · hello@pashutbook.com
    התנאים המלאים: pashutbook.com/terms

    לחיצה על "✅ נכון, לתשלום" היא הסכמה לתנאים.
    ```

  - **After payment** (`paid_customer`), send a short written summary (this is the
    "written document" the law requires): order number, date, price paid,
    delivery date, the cancellation/defect rules, business details, link to terms.
    The receipt app's message can do part of this.
  - Fill in `{days}` only after the print lab (task S.2) gives a turnaround. Be
    conservative, for example "עד 14 ימי עסקים". A missed promised date is
    itself a reason to cancel.

### 3. Short terms of service, agreed to inside WhatsApp without extra taps

- **Risk / law:** without terms, you have no written rules for defects, copyright,
  what "approve" means, or liability. Under the Standard Contracts Law (חוק החוזים
  האחידים), very one-sided terms are void anyway, so keep them **fair and short**.
  That's also more convincing to a court.
- **How to get binding agreement without hurting the flow:** use taps the customer
  already makes, plus a link:
  - **Welcome:** a notice (not a new button): *"by choosing a design you agree to
    the terms and privacy policy"* + link. The design tap becomes the agreement.
    Courts accept "browse-wrap" weakly and "click-wrap" well. A tap right under a
    clear sentence is close to click-wrap.
  - **Payment step:** the strongest agreement, because that's where the contract is
    really made (item 2 wording: *"לחיצה על ✅ נכון, לתשלום היא הסכמה לתנאים"*).
  - **Record it:** a history row such as `terms_accepted` with the terms' version
    (date). The bot already records every button tap, so this is a small addition
    later (rule 10). Keep old versions of the terms in the repo.
- **Suggested new welcome** (same length as today):

  ```
  שלום! 👋 ברוכים הבאים לפשוט בוק 📖
  שולחים תמונות מהטלפון ומקבלים אלבום מודפס ומעוצב.
  💰 ₪150 + ₪30 משלוח. משלמים רק אחרי שראיתם ואהבתם.

  1️⃣ בוחרים עיצוב
  2️⃣ שולחים תמונות
  3️⃣ אנחנו מעצבים ושולחים לכם לאישור

  בבחירת עיצוב אתם מסכימים לתנאים ולמדיניות הפרטיות:
  pashutbook.com/terms
  ```

- **Short terms text** (put on `pashutbook.com/terms`; Hebrew; a lawyer should
  review it once, about 1 hour of work):

  ```
  תנאי השימוש – פשוט בוק
  עודכן: {date}

  1. מי אנחנו: פשוט בוק, {owner name}, עוסק פטור {number}, {address}. hello@pashutbook.com
  2. השירות: אתם שולחים תמונות בוואטסאפ, אנחנו מעצבים אלבום, מדפיסים אותו אצל בית
     דפוס ושולחים אליכם. ההדפסה והמשלוח נעשים על ידי ספקים מטעמנו.
  3. מחיר: כפי שמופיע בשיחה לפני התשלום (כרגע ₪150 + ₪30 משלוח), כולל הכול.
  4. אישור: לפני ההדפסה תקבלו קישור לתצוגה מקדימה. "אהבתי" ותשלום = אישור של
     הסידור, הכותרת והתמונות כפי שהם בתצוגה. התצוגה מוקטנת; הצבעים בדפוס יכולים
     להיות מעט שונים מהמסך.
  5. ביטול: עד שהאלבום נשלח להדפסה, אפשר לבטל ולקבל החזר מלא. אחרי ההדפסה אין
     ביטול, כי האלבום מיוצר במיוחד עבורכם (תקנות הגנת הצרכן (ביטול עסקה)).
  6. פגם: אלבום פגום, שנפגע במשלוח או שונה ממה שאישרתם – כתבו לנו תוך 14 יום
     מקבלתו, עם תמונה של הבעיה, ונדפיס מחדש או נחזיר את הכסף. איכות התמונות
     המקוריות (למשל תמונה מטושטשת ששלחתם) אינה פגם.
  7. אספקה: עד {days} ימי עסקים מהתשלום. אם נאחר, נעדכן אתכם, ותוכלו לבטל.
  8. התמונות שלכם: התמונות שייכות לכם. אתם מאשרים שמותר לכם להדפיס אותן (למשל
     שלא צולמו על ידי צלם מקצועי שאסר זאת), ונותנים לנו רשות להשתמש בהן רק כדי
     להכין, להדפיס ולשלוח את האלבום. לא נשתמש בהן לשום דבר אחר ולא נפרסם אותן.
     מותר לנו לסרב להדפיס תמונות פוגעניות או כאלה שנראה שאינן שלכם.
  9. העיצוב: העיצובים והתבניות שייכים לפשוט בוק.
  10. פרטיות: לפי מדיניות הפרטיות, pashutbook.com/privacy. התמונות נמחקות
      אוטומטית (הפרטים שם).
  11. אחריות: האחריות שלנו מוגבלת לסכום ששילמתם על ההזמנה, חוץ ממה שהחוק לא
      מאפשר להגביל.
  12. מגבלות: אפשר לבקש עד 5 שינויים מכל סוג באלבום, ולהתחיל עד 3 אלבומים ביום.
  13. דין ושיפוט: דין ישראל.
  ```

- **Worst case without it:** every dispute becomes "your word against mine", and a
  copyright claim (item 9) lands on you alone.

### 4. Make the privacy page true, complete and shown at the start

- **Risk / law:** Privacy Protection Law, **section 11** (the notice when you collect
  data), strengthened by **Amendment 13 (in force since Aug 14, 2025)**. The notice
  must say: whether giving the data is required by law, **the purpose**, **who
  receives it**, and now also **what happens if the person refuses** and their
  **rights to see and correct** their data (sections 13–14). Amendment 13 gave the
  Privacy Protection Authority (הרשות להגנת הפרטיות) large administrative fines,
  and courts can award damages **without proof of harm**: up to ₪10,000 per
  person according to most summaries (some cite higher; ⚖️ confirm).
- **Gap 1: the notice isn't shown.** No customer message links to `/privacy`. The
  page exists only for Meta. Fix: the welcome link in item 3.
- **Gap 2: promises vs. what the code really does** (from `cleanup.py`,
  `history.py`, `behaviour.py`, `preview_links.py`):

  | The privacy page says | What really happens | Fix |
  |---|---|---|
  | "Photos are deleted automatically after the album is delivered." | Unpaid: 14 days after the last activity. Paid: 30 days **after payment** (no "delivered" step). Cancelled: within about 1 hour. | Say exactly this (wording below). |
  | Nothing about how long the order is kept. | The `orders` row keeps **phone, name, street, city and courier phone with no end date**. Only photos are deleted. | Decide a period (suggest: shipping details deleted 90 days after payment; the phone and order numbers kept for 7 years only if an accountant says you must). Then add the deletion to `cleanup.py` (a later task). |
  | "Measurement doesn't include phone numbers." | True literally, but every row has a **customer key made from the phone number** (HMAC), kept forever, and linked to the order (which has the phone). Under the law that's still personal data ("pseudonymous"), not anonymous. | Say "a coded number instead of the phone number". |
  | "Photos and order details are kept … on the business's computer." | Also: **cover photos, shipping addresses and help messages are sent to the owner's personal WhatsApp** (item 5), and Meta keeps uploaded preview images up to 30 days. | Mention both. |
  | Nothing about faces. | OpenCV finds **where** faces are, to avoid cutting them. It doesn't recognize **who** it is, and keeps no face "fingerprint". | Say so plainly; it prevents a scary misunderstanding (item 6). |
  | Nothing about the album page. | It keeps a random device code in the browser (localStorage) and reports scroll %, seconds, device type. | One line. |
  | "Delete everything on request within 30 days." | Fine, but there's no tool for it; it's manual. | Keep the promise; write a 5-line how-to for yourself (item 13). Also accept requests by WhatsApp ("עזרה"), not only email. |
  | "We may use AI (Anthropic Claude)." | Not used yet. | OK to keep. When added, Anthropic is in the US (see item 18). |
  | No business identity. | — | Name, business number, address, email (the "database owner"). |

- **Suggested new and replaced lines** (Hebrew part; mirror in English):

  ```
  מי אחראי על המידע: פשוט בוק, {owner name}, עוסק פטור {number}, {address}.
  privacy@pashutbook.com

  חובה למסור? לא. אין חובה בחוק למסור לנו מידע. בלי תמונות ובלי פרטי משלוח
  אי אפשר להכין ולשלוח אלבום.

  זיהוי פנים: המחשב מוצא איפה יש פנים בתמונה, רק כדי לא לחתוך אותן בעיצוב.
  הוא לא מזהה מי האדם, ולא שומר "טביעת פנים".

  מדידה: במקום מספר הטלפון אנחנו שומרים מספר מקודד, כדי לדעת אם לקוח חוזר.
  בדף האלבום נשמר בדפדפן קוד אקראי קטן, כדי לספור כמה מכשירים צפו באלבום.

  מי עוד מקבל מידע: וואטסאפ (Meta) מעבירה את ההודעות והתמונות. Supabase
  (באירופה, גרמניה) שומרת את התמונות ואת פרטי ההזמנה. Cloudflare מעבירה את
  הדף של האלבום. בית הדפוס מקבל את קובץ האלבום, וחברת השילוח את פרטי המשלוח,
  רק כדי להדפיס ולשלוח, ובהסכם שמחייב אותם לשמור על סודיות ולמחוק.

  מחיקה:
  • אלבום שלא שולם: התמונות והאלבום נמחקים 14 יום אחרי הפעולה האחרונה.
  • אלבום ששולם: התמונות והאלבום נמחקים 30 יום אחרי התשלום (כדי שנוכל להדפיס
    מחדש אם יש תקלה).
  • אלבום שהתחלתם מחדש: נמחק תוך שעה.
  • פרטי המשלוח נמחקים {N} ימים אחרי התשלום.
  • מספר ההזמנה והנתונים המספריים (בלי תמונות ובלי טקסטים) נשמרים כדי לשפר
    את השירות.

  הזכויות שלכם: אפשר לבקש לראות את המידע שלכם, לתקן אותו או למחוק אותו –
  בכתובת למטה או בוואטסאפ (כתבו "עזרה"). נענה תוך 30 יום.
  ```

- **Worst case:** a complaint to the Privacy Protection Authority (fines); a class
  action over a privacy promise that isn't kept ("deleted after delivery" while
  addresses stay forever). An untrue promise is worse than no promise.

### 5. Plug the copies outside the deletion system (your personal WhatsApp, its backups, logs)

- **Risk / law:** Privacy Protection Law + the Information Security Regulations
  (2017): personal data must be kept only where needed, secured, and deleted as
  promised. The bot sends **your personal phone** each customer's **cover photo**
  (`owner_request`), the **shipping address** (`owner_payment`), and help texts.
  These stay in your WhatsApp forever, in your phone's gallery if auto-save is on,
  and in your **iCloud / Google Drive WhatsApp backup**. That breaks the deletion
  promise and puts children's photos on a personal device that you also use for
  everything else.
- **Worst case:** a lost or hacked personal phone = a data breach (a "serious
  security incident" may have to be reported to the Authority). The privacy page
  becomes untrue.
- **Cheap fix (settings, no code):**
  - On your phone: WhatsApp → Settings → Chats → turn off **"Save to Photos" /
    media visibility** for the bot's chat.
  - Turn on **disappearing messages (7 days)** in the chat with the bot number. It
    deletes the copies on both sides automatically.
  - Exclude it from backup, or turn on **end-to-end encrypted backup**.
  - Phone locked with a code + Face ID; the Mac already has FileVault.
  - Later (task idea): send the owner the **preview link only**, not the cover
    image, and the city instead of the full address until payment.
  - Check what `bot.log` (on the Mac) contains. If it holds full phone numbers or
    addresses, rotate (delete) logs older than 30 days. I didn't read the code
    that writes it.

### 6. A one-page security and "database definitions" document, plus the cloud contracts

- **Risk / law:** Information Security Regulations (תקנות הגנת הפרטיות (אבטחת
  מידע), 2017) apply to almost every database, even a one-person one: a
  **database definitions document** (what data, why, where, who has access), basic
  security rules, access only for those who need it, and a plan for incidents.
  Amendment 13 narrowed **registration** of databases (now mainly data brokers and
  direct-marketing databases above 10,000 people, and public bodies), so you very
  likely **don't** need to register. But the security duties remain. Photos of
  children aren't "data of special sensitivity" by name, ⚖️ but a regulator will
  treat them as sensitive in practice.
- **Worst case:** a breach (for example a leaked Supabase secret key) + no
  documented security = fines and liability for every affected family.
- **Cheap fix (one evening):**
  - Write `docs/security.md` (private details stay out of the repo): data list,
    where it lives (Supabase Frankfurt, Mac, Meta, Cloudflare, owner phone, print
    lab), who has access (only you), deletion rules, what to do on a breach
    (change keys, tell the Authority and the affected customers if serious).
  - **2-step verification** on: Supabase, Meta Business, Cloudflare, GitHub, the
    business Gmail (already done), Apple ID.
  - Accept **Supabase's Data Processing Addendum (DPA)** (in its legal pages /
    dashboard). Cloudflare's and Meta's apply through their terms.
  - **Storage in the EU is allowed:** Israel's transfer-abroad regulations allow
    transfer to countries that apply the Council of Europe data convention
    (Germany does), and the EU recognizes Israel's law as adequate. ✅ No action,
    just mention it (item 4 wording).

### 7. A data-processing agreement with the print lab before the first file

- **Risk / law:** the Information Security Regulations (section 15, outsourcing)
  require a **written agreement** before an outside company gets access to your
  customers' data: what it may do, security, confidentiality, **deletion when
  done**, reporting breaches, no sub-contractors without approval. A print PDF is
  full of children's faces plus (for direct shipping) names and addresses.
- **Worst case:** the lab leaks or reuses files (for example as "samples" in its
  showroom or Instagram) and you're responsible to the customer.
- **Cheap fix:** don't wait for a big contract. A **one-page annex** that the lab
  signs or confirms by email is enough to start. Full list in item 15 (Tier 2).
  Minimum before the first file:

  ```
  1. הקבצים והפרטים שתקבלו מפשוט בוק משמשים רק להדפסה ולמשלוח של ההזמנה.
  2. סודיות מלאה. אין שימוש בתמונות לשום מטרה אחרת (גם לא כדוגמה או בפרסום).
  3. מחיקת הקבצים תוך 14 יום מהמשלוח, וגם מגיבויים בהזדמנות הראשונה.
  4. גישה רק לעובדים שצריכים אותה. אין העברה לספק משנה בלי אישור בכתב.
  5. דיווח מיידי (תוך 24 שעות) על כל דליפה או גישה לא מורשית.
  6. אנחנו רשאים לבקש אישור שהקבצים נמחקו.
  ```

### 8. Meta: the real number, a human path, and only service messages

- **Risk / policy:** WhatsApp Business Messaging Policy and Commerce Policy.
  - Photo books are an allowed product under the Commerce Policy. ✅
  - The **test number can't serve strangers** (5 numbers only), so Business
    Verification (task 0.4) is Tier 1 anyway, and it needs item 1.
  - **Opt-in:** the customer writes first and the bot only answers inside the
    24-hour window. ✅ Anything the business starts later (template messages)
    needs opt-in, and marketing needs more (item 9).
  - **A path to a human:** the policy expects bots to offer a clear way to reach a
    person (human handoff, email, phone). "עזרה" once a day + an email in the
    terms satisfies this. Keep it working; don't remove it in the spirit of rule
    12.
  - **Don't ask for card numbers or ID numbers in the chat** (forbidden by the
    policy). Today you don't. ✅ When you move to card payments, send a payment
    company link only.
  - **Honor "stop" requests** at once.
- **Worst case:** low quality rating → limits → a banned number, which ends the
  business overnight.
- **Cheap fix:** what's listed above, and read the policy page once more right
  before task 0.4 (it changes often; the latest version is dated Sep 2026).

---

## Tier 2: within the first 30 days, before growing

### 9. Spam law (section 30A, Communications Law): order updates yes, ads only with consent

- **Law:** an "advertising message" (דבר פרסומת) sent by electronic message (courts
  treat WhatsApp like SMS) needs the recipient's **prior explicit consent**.
  Damages **up to ₪1,000 per message without proof of harm**, and class actions are
  common. (Courts often award less, but don't count on it.)
- **What's allowed:**

  | Message | Allowed? |
  |---|---|
  | Everything in the order flow (count, preview link, approval, payment, "shipped", "delivered") | ✅ Service messages, not advertising. |
  | "Your album is waiting, want to finish?" (a reminder about **their own** order) | ✅ Probably fine **if it has no offer** in it. Adding "and 10% off!" turns it into an ad. One reminder at most. |
  | "How was the album? Rate us" | ⚠️ Grey. Keep it neutral, once, no offer, no link to buy. ⚖️ Courts are split on survey/review requests. |
  | "New: calendars! / holiday sale / order another album" | ❌ Advertising. Needs consent, or the existing-customer exception (below). |
  | Referral offer ("send a friend, get ₪20") | ❌ Advertising when you send it. Put it **inside the printed album** (QR) instead. That isn't covered by the law. |

- **The existing-customer exception (30A(c)):** a business may send ads about
  **similar products** to someone who gave their details **during a purchase**, if
  at that time they were told this and given a chance to refuse, and every ad lets
  them refuse. Safer and just as easy: **ask once, at the end** (after
  `paid_customer`), with buttons:

  ```
  רוצים שנעדכן אתכם מדי פעם על מבצעים ומוצרים חדשים? 🎁
  (אפשר להפסיק בכל רגע: כתבו "הסר")
  [כן, בשמחה] [לא תודה]
  ```

  Every marketing message must then **start with the word "פרסומת"**, name the
  business and contact details, and say how to stop ("להסרה כתבו: הסר"). Record
  consent and removal as history rows (rule 10). Also note: Meta requires its own
  opt-in for marketing templates and charges for them.
- **Fix the privacy page line** "we never use it for advertising" when (and only
  when) you start sending marketing to people who agreed.

### 10. Copyright: professional photos and other people's children

- **Law:** Copyright Act 2007. The **photographer owns the copyright** in a photo,
  even when the customer paid for the shoot, unless agreed otherwise. Printing it =
  copying it. Damages **up to ₪100,000 per infringement without proof of harm**
  (section 56). The photographer also has a "moral right" (credit, no distortion);
  cropping into a template is usually fine.
- **Realistic risk:** low for family phone photos (the customer took them).
  Higher for newborn, bar mitzvah, wedding and kindergarten-photographer shoots.
  Photographers in Israel do sue print shops.
- **Other people's children:** printing a private family album isn't "publishing",
  so the Privacy Law's "publishing a photo" ban isn't triggered. Risk is low, as
  long as nothing is ever shown publicly. The terms make the customer confirm they
  may use the photos.
- **Cheap fix:**
  - The terms' item 8 (customer confirms the right + allows you to refuse).
  - During your approval, if you see a **studio watermark or logo**, ask the
    customer whether they have permission.
  - A simple takedown rule: if a photographer complains, stop, check, reply in
    writing.
  - **Never use customer albums in your marketing** (item 17).

### 11. Accessibility of the preview page and pashutbook.com

- **Law:** Equal Rights for Persons with Disabilities Law + the Service
  Accessibility Regulations (תקנה 35): websites that serve the public must meet
  Israeli Standard 5568 (WCAG AA) and publish an **accessibility statement
  (הצהרת נגישות)**. Damages **without proof of harm up to about ₪50,000**, and
  this is one of Israel's busiest class-action fields.
- **Exemption:** the regulations exempt very small businesses (a full exemption
  for a עוסק פטור with low turnover, around ₪100,000–120,000 a year according to
  the sources I found; the sources disagree on the exact numbers). ⚖️ Ask a lawyer
  whether you're exempt now, and when it ends. **Do the cheap fixes anyway**:
  grandparents are often people with weaker eyesight, so this is good business
  too.
- **Cheap fixes:**
  - On the preview page: give each picture a description in `alt` (today it's
    empty), e.g. `alt="עמוד 5 ועמוד 6"`; allow zoom (don't block pinch-zoom);
    check colour contrast; keep the text big.
  - `lang="he" dir="rtl"` is already set. ✅
  - Put an **accessibility statement** on pashutbook.com (what was done, what's
    known not to work, a contact for accessibility requests: hello@pashutbook.com).
  - Don't buy an "accessibility widget/plugin" (nagishut plugins). They don't
    give legal protection and are sometimes the reason for claims.

### 12. Decide how long the order details are kept, and delete them by themselves

- **Law:** Privacy Protection Law (purpose limitation, data minimization under
  Amendment 13) + your own privacy page.
- **Today:** photos are cleaned up; the `orders` row (phone, name, street, city,
  courier phone) stays forever.
- **Fix:** ask an accountant what you must keep for tax (the **receipt** keeps name
  and amount for 7 years, in the receipts app). The address in Supabase isn't
  needed after delivery. Suggest: empty the `ship_*` fields **90 days after
  payment**, keep the order's numbers and the coded customer key for statistics.
  This is a small later task in `cleanup.py`; update the privacy page with the
  same numbers.

### 13. A simple routine for "show me / fix / delete my data" requests

- **Law:** sections 13–14 (right to see and correct), and your privacy promise to
  delete within 30 days.
- **Fix:** a 5-line note for yourself: how to find the order by phone, how to run
  the cleanup for one order, how to empty its shipping fields, and a reply
  template. Keep a small list (date, request, date done). The bot's "עזרה" brings
  these requests to you.

### 14. Defects, delays and reprints: a promise you can keep

- **Law:** Consumer Protection Law (a defective product and late delivery are
  reasons to cancel; misleading the customer is forbidden, section 2).
- **Risk:** with a supplier printing and shipping, **the customer holds you
  responsible** (the lesson in README from EverTiles). Remember that paid albums'
  photos are deleted 30 days after payment: a reprint after that is impossible
  unless the print PDF is kept.
- **Fix:** promise a delivery window you can meet; ask for a photo of a defect
  within 14 days; budget reprints (the README's ₪5 "reprint margin"); make the 30
  days count from **delivery** once there's a delivered step, or keep the print
  PDF until then.

### 15. The full print lab contract

When choosing the lab (task S.2), the agreement (or the lab's order terms plus your
annex) should cover:

- **Data (item 7):** purpose, confidentiality, deletion after X days, no
  sub-contractors, breach reporting, no use as samples.
- **Quality:** what counts as a defect (colour shift beyond a tolerance, banding,
  cut-off, binding, wrong page order); free **reprint at the lab's cost** for its
  mistakes; who decides (a photo is enough).
- **Time:** turnaround in working days; what happens when late (the lab pays for
  express shipping or a discount).
- **Shipping (if the lab ships direct):** plain packaging with no lab branding (so
  the customer isn't sent to the lab); who pays for loss/damage in transit.
- **Ownership:** **your templates, designs and files are yours**; the lab gets no
  rights in them and may not copy them for others.
- **Non-solicitation:** the lab doesn't contact or sell to your customers.
- **Prices:** fixed for a period; notice before changes.
- **Ending:** what happens to files and open orders if you part ways.

### 16. Payments later: a payment company, never card data in the chat

When you move from Bit to Grow / PayPlus / Cardcom: use their **hosted payment
link** only, so card numbers never touch your bot, Supabase or WhatsApp (also
required by Meta, item 8, and the card industry's PCI rules). Their receipt can
replace the separate receipts app.

---

## Tier 3: can wait

### 17. Using albums or customer photos in marketing

Don't. Use stock photos (already the plan for the example albums in S.3). If you
ever want a real customer's album as an example, get a **separate, explicit
written consent** (not inside the terms), and remember the children in it can't
consent themselves.

### 18. When Claude (AI) is added

Anthropic is in the US, so customer texts would go abroad. Under the Israeli
transfer rules this is allowed with suitable protections (a contract: Anthropic's
commercial terms include a DPA and no training on API data). Update the privacy
page line from "may" to "does", send only the text that's needed (not photos,
unless photo choice is added), and check Meta's current rules for AI in WhatsApp
Business (Meta restricts general-purpose AI chatbots since 2026; a bot that serves
your own customers is allowed). ⚖️ Quick check with the lawyer then.

### 19. More languages (Russian, Arabic, English)

Terms, privacy page and the payment disclosure must exist **in the language of the
conversation**. A customer who can't read the terms isn't bound by them in
practice. Translate them together with each campaign.

### 20. Growth thresholds

Watch for: more than **10,000 people** in a direct-marketing database (registration
duty with the Authority); turnover above the עוסק פטור ceiling (move to עוסק
מורשה, prices then include 18% VAT, which must be in the shown price); moving off
the Mac (then a proper cloud DPA, and update the privacy page); hiring help (they
need access rules and a confidentiality signature). Consider cheap **professional
and cyber insurance** once volume grows.

---

## Questions for a real Israeli lawyer (one meeting, about 1–2 hours)

Bring this file, the privacy page and the terms draft.

1. Does the **made-to-order exception** fully cover a personal photo album, so the
   customer can't cancel after printing? Is "cancel free until it's sent to print"
   the right line?
2. Does the **extended cancellation (up to 4 months) for seniors 65+, people with
   disabilities and new immigrants** apply to a sale through a WhatsApp bot? If
   so, does the made-to-order exception still win?
3. Is a **WhatsApp message** a valid "written document" for the remote-sale
   disclosure (section 14C)? Must it include my **home address**, or is a PO box /
   email enough?
4. Is the **agreement method** (notice at the design tap + "agree" in the payment
   button + a link) enough for the terms to bind?
5. Please review the **terms** and the **privacy page** wording once (Amendment 13
   notice items, statutory damages amounts, the "coded customer key").
6. Are photos of children, and **face detection** that only finds where faces are,
   "data of special sensitivity" or biometric data under Amendment 13? Anything
   extra to do?
7. Which level of the **Information Security Regulations** applies to a one-person
   business with a few hundred customers? Is my one-page document enough?
8. Am I **exempt from website accessibility** as a small עוסק פטור? Until when?
9. Is a **neutral review request** after delivery an advertisement under section
   30A? Is the consent button wording in item 9 good?
10. Is the **liability cap** (the amount paid) valid under the Standard Contracts
    Law?
11. For the accountant, not the lawyer: עוסק פטור vs. בעל עסק זעיר, how long to keep
    order records, Bit for business.

---

## Sources

Checked on Nov 27, 2026. Secondary summaries were used where the official text
wasn't reachable; that's one more reason for the lawyer meeting.

- Privacy Protection Law, Amendment 13:
  [IAPP](https://iapp.org/news/a/israel-marks-a-new-era-in-privacy-law-amendment-13-ushers-in-sweeping-reform),
  [Library of Congress](https://www.loc.gov/item/global-legal-monitor/2025-11-17/israel-amendment-to-privacy-protection-law-goes-into-effect/),
  [Gornitzky](https://www.gornitzky.com/an-amendment-to-the-israeli-protection-of-privacy-law-will-increase-exposure-for-violation-of-data-protection-requirements/),
  [Goldfarb](https://www.goldfarb.com/amendment-13-to-the-israeli-privacy-protection-law/),
  [DLA Piper](https://www.dlapiperdataprotection.com/?c=IL),
  [Chambers 2026](https://practiceguides.chambers.com/practice-guides/data-protection-privacy-2026/israel),
  [Baker McKenzie (penalties)](https://resourcehub.bakermckenzie.com/en/resources/global-data-and-cyber-handbook/emea/israel/topics/regulators-enforcement-priorities-and-penalties),
  [Pearl Cohen](https://www.pearlcohen.com/the-knesset-enacts-a-comprehensive-amendment-to-the-privacy-protection-law/),
  [Linklaters](https://www.linklaters.com/insights/data-protected/data-protected---israel)
- Remote sales and cancellation:
  [כל זכות: עסקת מכר מרחוק](https://www.kolzchut.org.il/he/עסקת_מכר_מרחוק),
  [כל זכות: ביטול עסקת מכר מרחוק](https://www.kolzchut.org.il/he/ביטול_עסקת_מכר_מרחוק),
  [כל זכות: עסקה צרכנית שלא ניתן לבטל](https://www.kolzchut.org.il/he/עסקה_צרכנית_שלא_ניתן_לבטל),
  [כל זכות: ביטול על ידי אדם עם מוגבלות](https://www.kolzchut.org.il/he/ביטול_עסקה_ברוכלות_או_עסקת_מכר_מרחוק_על_ידי_אדם_עם_מוגבלות),
  [לשכת המסחר: מוצר שיוצר במיוחד](https://www.chamber.org.il/serviceslobby/legal/1857/85665/),
  [Protocol: no cancellation right](https://protocol.co.il/consumer-transaction-cancellation-no-right/)
- Spam law:
  [כל זכות: חוק הספאם](https://www.kolzchut.org.il/he/פיצוי_בגין_משלוח_דברי_פרסומת_ללא_הסכמה_של_הנמען_(חוק_הספאם)),
  [לשכת המסחר: רענון נהלים](https://www.chamber.org.il/serviceslobby/legal/74023/115485/),
  [Globes: Supreme Court on spam](https://www.globes.co.il/news/article.aspx?did=1001264492),
  [Bizportal: spam claims 2026](https://www.bizportal.co.il/additives/429/spam-claim.html)
- Copyright:
  [TAU: statutory damages](https://law.tau.ac.il/sites/law.tau.ac.il/files/media_server/law_heb/shiip/Legislative%20Watch%20%E2%80%93%20SHIIP%20on%20Statutory%20Damages.pdf),
  [Calcalist](https://www.calcalist.co.il/articles/0,7340,L-3794190,00.html)
- Accessibility:
  [כל זכות: פטור מחובת הנגשה לאתרים](https://www.kolzchut.org.il/he/פטור_מחובת_הנגשה_לאתרי_אינטרנט_ואפליקציות),
  [לשכת המסחר: תיקון נגישות שירותי אינטרנט](https://www.chamber.org.il/serviceslobby/legal/1859/2151/),
  [gov.il: exemption request](https://www.gov.il/he/service/application_for_exemption_internet_people_with_disabilities)
- Meta / WhatsApp:
  [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/),
  [Meta: getting opt-in](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in)
- Tax and payments:
  [Bizportal: עוסק פטור vs. מורשה 2026](https://www.bizportal.co.il/additives/312/vat-dealer-status-ca.html),
  [Green Invoice: תקרת עוסק פטור](https://www.greeninvoice.co.il/magazine/%D7%AA%D7%A7%D7%A8%D7%AA-%D7%A2%D7%95%D7%A1%D7%A7-%D7%A4%D7%98%D7%95%D7%A8/),
  [כל זכות: עוסק פטור](https://www.kolzchut.org.il/he/%D7%A2%D7%95%D7%A1%D7%A7_%D7%A4%D7%98%D7%95%D7%A8),
  [gov.il: בעל עסק זעיר](https://www.gov.il/he/service/request-transfer-to-micro-business-owner)
