# S.2: Printer quote

**Goal:** get prices and file rules from 3 Israeli printers, then choose one.
**Who:** you (email or phone). **Time:** about 1 hour to send, then wait 2–7 days for replies.

When the replies come back, open a new conversation ("S.2 replies") and paste them in. I'll put them in the table, update the price calculator, and change `album/printer.py` and the page size in `album/designs.py` to match the chosen printer.

---

## 1. Who to contact

I found these online (Nov 26, 2026). I could not check their prices for a 20×20 cm book made from our own PDF: only their reply will tell. Start with the first 3, and add more if one doesn't answer within 3 days.

| # | Printer | Why | Seen online |
|---|---|---|---|
| 1 | **דיפרינט / אלבומים** — [dprint.co.il](https://dprint.co.il/) · [albumim.co.il](https://albumim.co.il/) | A photo lab (real photo paper, semi-matte). Says it prints a hardcover album **from your own PDF** | From ₪255 for a hardcover up to A4 (retail price; ask for a business price) |
| 2 | **C-Book** — [cbook.co.il](https://cbook.co.il/product/regular-20x20-fixed/) | Sells a **square 20×20** album | ₪65 softcover; hardcover costs extra |
| 3 | **פוקוס דיגיטל** — [focusdigital.co.il](https://www.focusdigital.co.il/photo-lab) | A lab that works **for professional photographers** (the kind of supplier we want: they print, we sell) | No prices online |
| 4 | **לופה** — [lupa.co.il](https://www.lupa.co.il/) | The best-known album maker in Israel. Ask if they print a ready PDF for a business | Retail prices on their site |
| 5 | **מישלי ארט** — [mishely-art.com](https://www.mishely-art.com/%D7%9E%D7%97%D7%99%D7%A8%D7%95%D7%9F-%D7%90%D7%9C%D7%91%D7%95%D7%9E%D7%99%D7%9D) | Has an album price list | Price list on their site |

### Near Kfar Yona (owner's request, Nov 26, 2026)

Close is good: you can pick up the first ~10 books yourself and check them (see ROADMAP.md). Found in business directories; not checked whether they print a whole album from our PDF. Call or visit.

| # | Business | Where | Why | Contact (from directories) |
|---|---|---|---|---|
| 6 | **מומנטו מדיה** — [momento.co.il](https://www.momento.co.il/) | Kfar Mall, שרת 6, כפר יונה (also ויצמן 4, נתניה) | Photo shop that sells albums. Many shops send albums to a big lab: **ask which lab prints them**, that lab could become our supplier | 09-8987167, WhatsApp 050-8989237 |
| 7 | **גולדפרינט** — [goldprint.co.il](https://www.goldprint.co.il/) | Poleg industrial area, נתניה | Digital print shop (prints one copy from a file). Ask about a hardcover photo book | 09-8850771 |
| 8 | **דפוס המגנטון** — [hamagneton.co.il](https://hamagneton.co.il/%D7%90%D7%95%D7%93%D7%95%D7%AA%D7%99%D7%A0%D7%95/) | נתניה | Print house in the Sharon | on their site |
| 9 | **דפוס דיגיטל** — [dfusdigital.co.il](https://dfusdigital.co.il/) | location not stated: check | Says it makes **hardcover books** (2 mm board), including photo albums | on their site |

Two in Kfar Yona (טל פרינט, שי הדפסות) print documents and signs, not albums: skip.

**On the phone with a local shop**, add: "אפשר לאסוף בעצמי מהחנות?" (can I pick it up myself?) and "מי מדפיס לכם את האלבומים?" (who prints your albums?).

**Benchmark (no need to contact):** Prodigi, an overseas printer that ships to Israel, about **$25** for a 21×21 hardcover before shipping (see `docs/research-notes.md`, section 6).

---

## 2. The email (copy, fill in your name, send)

Use your business email if it works, otherwise your own. Don't attach customer photos.

> **נושא:** בקשת הצעת מחיר — הדפסת אלבומי תמונות מקובץ PDF לעסק
>
> שלום,
>
> אני מקים עסק קטן של אלבומי תמונות (Pashut Book). אנחנו מעצבים את האלבום בעצמנו ושולחים קובץ PDF מוכן להדפסה. מתחילים בכ-10 אלבומים בחודש הקרוב, ומקווים לגדול ל-30–50 בחודש. כל אלבום הוא עותק אחד.
>
> אשמח לדעת:
> 1. **מחיר לאלבום אחד** בכריכה קשה, בגודל 20×20 ס"מ (או הגודל הריבועי הקרוב שלכם), ב-24, 32 ו-40 עמודים. האם יש מחיר לעסקים או הנחה לפי כמות?
> 2. **אילו גדלים** יש לכם (ריבועי ולרוחב), ומה המחיר של כל אחד?
> 3. **נייר:** סוג הנייר (נייר צילום / דפוס דיגיטלי), מט או מבריק, ועובי.
> 4. **כריכה:** כריכה קשה עם תמונה מודפסת? האם יש שדרה (גב)? אפשר לכתוב עליה בעברית?
> 5. **כריכה מימין:** האם אפשר אלבום שנפתח מימין לשמאל (עברית)?
> 6. **הדרישות לקובץ:** גודל העמוד, שוליים לחיתוך (bleed), רזולוציה (DPI), RGB או CMYK, קובץ אחד או כריכה בנפרד, מספר עמודים מינימלי ומקסימלי.
> 7. **זמן הכנה:** כמה ימי עבודה מקבלת הקובץ ועד שהאלבום מוכן?
> 8. **משלוח:** אפשר לשלוח ישירות ללקוח שלנו, באריזה בלי מחיר ובלי השם שלכם? כמה זה עולה, ותוך כמה ימים?
> 9. **הזמנה:** איך שולחים קובץ (מייל, העלאה לאתר, ממשק API)? האם תעדכנו כשהאלבום הודפס ונשלח?
> 10. **תשלום:** חשבונית לעסק, אשראי או העברה? תשלום לכל הזמנה או פעם בחודש?
> 11. **אלבום לדוגמה:** אפשר להזמין אלבום ניסיון אחד במחיר רגיל כדי לבדוק איכות?
> 12. **בונוס:** האם אתם מדפיסים גם דפים בודדים (בלי כריכה), כריכת ספירלה, או לוחות שנה?
>
> תודה רבה,
> [השם שלך]
> Pashut Book
> [טלפון]

**On the phone:** use the same list. Questions 1, 6 and 8 matter most.

---

## 3. What to look for in the replies

| Matters most | Why |
|---|---|
| Price for 24 pages, hardcover | The calculator guesses ₪60. At our ₪150 price, every ₪10 more cuts profit by ₪10 |
| Takes our PDF | Our bot makes the PDF. A printer that only works through its own editor doesn't fit |
| Ships straight to the customer, plain package | Saves your time later (the first ~10 books still come to you for checking: see ROADMAP.md) |
| Right-side binding | Hebrew books open from the right |
| Days to the door | Customers expect about a week |

**Warning signs:** "only through our app/editor", a minimum order of many copies, no sample book.

## 4. Fill in as replies arrive

| | דיפרינט | C-Book | פוקוס | לופה | Prodigi (benchmark) |
|---|---|---|---|---|---|
| Price, 24 pages, hardcover | | | | | ~$25 + shipping |
| Price, 40 pages | | | | | |
| Size | | | | | 21×21 |
| Takes our PDF? | | | | | ✅ |
| Right binding? | | | | | ❌ (mirrored file) |
| Ships to customer? Cost | | | | | ✅ abroad, slow |
| Days to the door | | | | | ~14–21 |
| File rules (bleed, DPI, colour) | | | | | no bleed, 300 DPI, RGB |

**Done when:** one printer is chosen and you have their file rules. Then S.4: order one test album from WhatsApp HD photos.
