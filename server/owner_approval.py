"""The owner approves every album before printing (task 3.1).

How it works:
1. The customer taps "😍 אהבתי!" on their album. orders.py calls start().
2. In the background, this makes the print files (album/print_pdf.py, with the
   .venv Python, like the album itself) and reads their check: photos that
   would print blurry, a wrong page count, and the album's own notes.
3. It sends the OWNER (OWNER_PHONE in .env) on WhatsApp:
   - the cover with a button that opens the same preview page the customer got,
   - the facts and anything worth checking,
   - buttons [✅ לאשר] [⚠️ יש בעיה].
4. "Approve": the order gets the note "approved", the customer hears that the
   album is ready for printing, and the owner gets the print files' place on the Mac.
   "Problem": the bot asks the owner to type a short message, and sends it to
   the customer as is (with a [✏️ לשנות משהו] button). The order stays waiting.
5. Anything the customer types after "love it" is passed to the owner, with
   buttons [💬 לענות] [✅ לאשר].
6. The owner can type "אישורים" to get all albums still waiting again (for
   example after WhatsApp's 24-hour window closed, see below).

Payment (task 3.2): after "approve", the customer sends a shipping address and
confirms it. Then the owner gets "send a Bit request of ₪X to 05…" with the
address and a [💰 התקבל תשלום] button. The owner sends the Bit request by hand
from their own Bit app, and taps the button when the money arrives: the
customer hears the album is going to print. "אישורים" also resends these.

Help (task 3.2): a customer's question after "עזרה" (text only, once a day)
comes with a [💬 לענות] button; the owner's typed answer goes to the customer
as is, without buttons. Answering is the owner's choice.

If the customer changes anything, the album is built again, and the old
request's buttons stop working (each request has its own code in the button);
a new request comes when the customer loves the new version.

WhatsApp's 24-hour rule: the bot may send free messages only to someone who
wrote to it in the last 24 hours. This is true for the owner too. If the owner
hasn't written to the bot for a day, Meta drops the request (bot.py logs it).
Then type anything to the bot, e.g. "אישורים". A paid "template" message
would avoid this; not needed while the owner talks to the bot every day.

The owner's phone may also be a test customer's phone: only the owner's buttons
(their ids start with "owner_"), the word "אישורים", and the message typed after
"problem" are handled here; everything else goes to the normal conversation.
"""

import json
import logging
import re
import secrets
import subprocess
import threading
import time

import conversation
import preview_links
from orders import short
from settings import PROJECT_DIR

log = logging.getLogger("bot")

ALBUM_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
PRINT_SCRIPT = PROJECT_DIR / "album" / "print_pdf.py"
ALBUMS_DIR = PROJECT_DIR / "output" / "albums"
TOOL_SECONDS = 20 * 60
# At most this many lines of each kind of check in the owner's message.
MAX_LINES = 5


def owner_number(value):
    """The owner's number as WhatsApp writes it (972…, digits only).
    "050-123-4567" and "+972 50 123 4567" both become "972501234567"."""
    digits = "".join(c for c in value or "" if c.isdigit())
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return digits or None


class OwnerApprovals:
    def __init__(self, orders, send, texts, owner_phone, public_url, run_print=None):
        self.orders = orders
        self.send = send            # send(phone, message) -> True if sent
        self.texts = texts
        self.owner = owner_number(owner_phone)
        self.public_url = public_url.rstrip("/")
        self.run_print = run_print or run_print_tool
        # (phone, order_id, help?): the owner is typing a message for this customer
        self._writing = None
        self._guard = threading.Lock()

    # ---------- asking the owner ----------

    def start(self, phone, order_id):
        """Ask the owner to approve this album, in the background (called by orders.py)."""
        if not self.owner:
            log.warning("Album %s is waiting for approval, but OWNER_PHONE is not set in .env",
                        short(order_id))
            return
        threading.Thread(target=self._safe_ask, args=(phone, order_id), daemon=True).start()

    def _safe_ask(self, phone, order_id):
        try:
            self.ask(phone, order_id)
        except Exception:
            log.exception("Something went wrong while asking the owner about %s",
                          short(order_id))

    def ask(self, phone, order_id):
        started = time.monotonic()
        report = self.run_print(order_id)
        token = secrets.token_hex(3)
        if not self.orders.owner_asked(phone, order_id, token):
            log.info("Album %s changed before the owner was asked; a new request comes later",
                     short(order_id))
            return
        self._record(phone, order_id, "owner_asked", detail="print_failed"
                     if report is None or "error" in report else None,
                     info=dict(_report_numbers(report),
                               seconds=round(time.monotonic() - started, 1)))
        self._send_request(phone, order_id, token, report)
        log.info("Album %s: asked the owner to approve it", short(order_id))

    def _send_request(self, phone, order_id, token, report=None):
        t = self.texts
        info = self.orders.info(phone, order_id) or {}
        folder = ALBUMS_DIR / short(order_id)
        code, link = preview_links.current(folder)
        facts = {"order": _ltr(short(order_id)), "phone": _last_digits(phone),
                 "pages": link["pages"] if link else "?",
                 "photos": (link or {}).get("photos") or info.get("photos", "?"),
                 "design": t.get("design_" + str(info.get("design")), "?"),
                 "title": info.get("title") or t["no_title"]}
        text = t["owner_request"].format(**facts)
        changes = conversation.photo_changes(info) if info.get("notes") else []
        if changes:
            text += "\n" + t["owner_photo_changes"].format(list=", ".join(
                c.replace("removed:", "🗑️ ").replace("replaced:", "📷 ").replace(":", "→")
                for c in changes))
        checks = self._checks(report)
        if checks:
            text += "\n\n" + checks
        if link:
            cover = folder / "preview" / link["images"][0]["name"]
            # "?o=1": the owner's own visits aren't counted as the customer's (3.3b).
            message = {"text": text, "link": {"button": t["button_preview_link"],
                                              "url": f"{self.public_url}/album/{code}?o=1"}}
            if cover.is_file():
                message["image_file"] = str(cover)
            self.send(self.owner, message)
        else:
            self.send(self.owner, {"text": text + "\n\n" + t["owner_no_link"]})
        self.send(self.owner, {"text": t["owner_decide"], "buttons": [
            {"id": f"owner_ok:{order_id}:{token}", "title": t["button_owner_ok"]},
            {"id": f"owner_problem:{order_id}:{token}", "title": t["button_owner_problem"]},
        ]})

    def _checks(self, report):
        """What the owner should look at, from the print tool's report."""
        t = self.texts
        if report is None:
            return ""   # resending a waiting request: the print files were checked before
        if "error" in report:
            return t["owner_print_failed"].format(error=report["error"])
        lines = []
        # Only what really needs a look: photos that would print blurry (❌, under
        # 150 DPI) and the album's own notes (📝). Photos at 150-199 DPI, e.g. every
        # photo sent without HD (195), print fine: one summary line, not a list.
        for kind, items in (("❌", report.get("problems", [])), ("📝", report.get("notes", []))):
            lines += [f"{kind} {in_hebrew(item, t)}" for item in items[:MAX_LINES]]
            if len(items) > MAX_LINES:
                lines.append(t["owner_more"].format(count=len(items) - MAX_LINES))
        text = t["owner_print_check"] + "\n" + "\n".join(lines) if lines else t["owner_print_ok"]
        soft = len(report.get("warnings", []))
        if soft:
            text += "\n" + t["owner_print_soft"].format(count=soft)
        return text

    # ---------- the owner's messages ----------

    def handles(self, sender, kind, value):
        """Is this message from the owner, for the owner's part of the bot?"""
        if not self.owner or sender != self.owner:
            return False
        if kind == "button":
            return value.startswith("owner_")
        if kind == "text":
            with self._guard:
                if self._writing:
                    return True
            return _clean(value) in [_clean(w) for w in self.texts["owner_pending_words"]]
        return False

    def handle(self, kind, value):
        """Answer one of the owner's messages (handles() said yes)."""
        t = self.texts
        if kind == "text":
            with self._guard:
                writing, self._writing = self._writing, None
            if writing:
                self._pass_on(writing, value)
            else:
                self.resend_waiting()
            return
        action, _, rest = value.partition(":")
        order_id, _, token = rest.partition(":")
        phone = self.orders.phone_of(order_id)
        if not phone:
            self.send(self.owner, {"text": t["owner_old"]})
            return
        if action == "owner_paid":
            self._paid(phone, order_id)
            return
        if action in ("owner_write", "owner_help"):
            help_answer = action == "owner_help"
            with self._guard:
                self._writing = (phone, order_id, help_answer)
            self.send(self.owner, {"text": t["owner_write_help" if help_answer else "owner_write"]})
            return
        decision = "approved" if action == "owner_ok" else "owner_problem"
        result = self.orders.owner_decided(phone, order_id, token, decision)
        if result != "ok":
            self.send(self.owner, {"text": t["owner_" + result]})
            return
        if decision == "approved":
            sent = self.send(phone, {"text": t["owner_approved_customer"]})
            files = sorted((ALBUMS_DIR / short(order_id)).glob("print-*.pdf"))
            self.send(self.owner, {"text": t["owner_approved"].format(
                order=_ltr(short(order_id)),
                files="\n".join(_ltr(f.name) for f in files) or t["owner_no_files"],
                folder=_ltr(str(ALBUMS_DIR / short(order_id))))
                + ("" if sent else "\n\n" + t["owner_not_sent"])})
            log.info("✅ Album %s approved by the owner", short(order_id))
        else:
            with self._guard:
                self._writing = (phone, order_id, False)
            self.send(self.owner, {"text": t["owner_write"]})
            log.info("Album %s: the owner found a problem", short(order_id))

    def _record(self, phone, order_id, event, **values):
        """A moment in the order history (task 3.3). Numbers only."""
        record = getattr(self.orders, "record_for", None)
        if record:
            record(phone, order_id, event, **values)

    # ---------- payment (task 3.2) ----------

    def payment(self, phone, order_id):
        """The customer confirmed the address: ask the owner to send a Bit
        request (called by orders.py, with the customer's order locked)."""
        if not self.owner:
            log.warning("Order %s is waiting for payment, but OWNER_PHONE is not set in .env",
                        short(order_id))
            return
        threading.Thread(target=self._safe_payment, args=(phone, order_id), daemon=True).start()

    def _safe_payment(self, phone, order_id):
        try:
            self.send_payment_request(phone, order_id)
        except Exception:
            log.exception("Could not ask the owner to collect payment for %s", short(order_id))

    def send_payment_request(self, phone, order_id):
        t = self.texts
        info = self.orders.info(phone, order_id) or {}
        _, _, total = conversation.payment_amounts()
        self.send(self.owner, {"text": t["owner_payment"].format(
            order=_ltr(short(order_id)), total=info.get("price") or total,
            phone=_ltr(local_number(phone)), address=conversation.shipping_text(info.get("ship"))),
            "buttons": [{"id": f"owner_paid:{order_id}", "title": t["button_owner_paid"]}]})
        log.info("Order %s: asked the owner to collect the payment", short(order_id))

    def _paid(self, phone, order_id):
        t = self.texts
        result = self.orders.owner_paid(phone, order_id)
        if result == "already":
            self.send(self.owner, {"text": t["owner_paid_already"]})
            return
        if result != "ok":
            self.send(self.owner, {"text": t["owner_old"]})
            return
        sent = self.send(phone, {"text": t["paid_customer"]})
        self.send(self.owner, {"text": t["owner_paid"].format(
            order=_ltr(short(order_id)), folder=_ltr(str(ALBUMS_DIR / short(order_id))))
                               + ("" if sent else "\n\n" + t["owner_not_sent"])})
        log.info("💰 Order %s paid", short(order_id))

    def _pass_on(self, writing, text):
        """The owner's typed message goes to the customer, as is."""
        t = self.texts
        phone, order_id, help_answer = writing
        if _clean(text) in [_clean(w) for w in t["owner_cancel_words"]]:
            self.send(self.owner, {"text": t["owner_cancelled"]})
            return
        message = {"text": t["team_message"].format(text=text.strip())}
        if not help_answer:
            message["buttons"] = [{"id": "edit_menu", "title": t["button_edit"]}]
        sent = self.send(phone, message)
        self._record(phone, order_id, "owner_wrote", detail="help" if help_answer else None,
                     info={"letters": len(text.strip()), "sent": sent})
        reply = t["owner_passed_on"] if sent else t["owner_not_sent"]
        self.send(self.owner, {"text": reply.format(phone=_last_digits(phone))})
        log.info("Album %s: passed the owner's message to the customer", short(order_id))

    def customer_text(self, phone, order_id, text):
        """The customer typed something after "love it": pass it to the owner.
        (Called while the customer's order is locked, so it runs in the background.)"""
        if not self.owner:
            log.warning("A customer wrote to the team, but OWNER_PHONE is not set in .env")
            return
        threading.Thread(target=self._safe_tell, args=(phone, order_id, text),
                         daemon=True).start()

    def _safe_tell(self, phone, order_id, text):
        try:
            self.tell_owner(phone, order_id, text)
        except Exception:
            log.exception("Could not pass a customer's message to the owner")

    def tell_owner(self, phone, order_id, text):
        t = self.texts
        buttons = [{"id": f"owner_write:{order_id}", "title": t["button_owner_write"]}]
        info = self.orders.info(phone, order_id) or {"notes": []}
        token = self.orders.owner_token(phone, order_id)
        if token and "approved" not in info["notes"]:
            buttons.append({"id": f"owner_ok:{order_id}:{token}", "title": t["button_owner_ok"]})
        if "payment_wait" in info["notes"]:
            buttons.append({"id": f"owner_paid:{order_id}", "title": t["button_owner_paid"]})
        self.send(self.owner, {"text": t["owner_customer_wrote"].format(
            phone=_last_digits(phone), order=_ltr(short(order_id)), text=text), "buttons": buttons})

    # ---------- help (task 3.2) ----------

    def help_request(self, phone, order_id, text):
        """A customer's question after "עזרה": to the owner, with [💬 לענות].
        (Called while the customer's order is locked, so it runs in the background.)"""
        if not self.owner:
            log.warning("A customer asked for help, but OWNER_PHONE is not set in .env")
            return
        threading.Thread(target=self._safe_help, args=(phone, order_id, text),
                         daemon=True).start()

    def _safe_help(self, phone, order_id, text):
        try:
            self.send_help(phone, order_id, text)
        except Exception:
            log.exception("Could not pass a help request to the owner")

    def send_help(self, phone, order_id, text):
        t = self.texts
        self.send(self.owner, {"text": t["owner_help"].format(
            phone=_last_digits(phone), order=_ltr(short(order_id)), text=text),
            "buttons": [{"id": f"owner_help:{order_id}", "title": t["button_owner_write"]}]})
        log.info("Order %s: the customer asked for help", short(order_id))

    def resend_waiting(self):
        """The owner typed "אישורים": send every album still waiting for approval
        or for payment again."""
        waiting = self.orders.waiting_for_owner()
        paying = self.orders.waiting_for_payment()
        if not waiting and not paying:
            self.send(self.owner, {"text": self.texts["owner_none_waiting"]})
            return
        for phone, order_id in waiting:
            token = self.orders.owner_token(phone, order_id)
            if token:
                self._send_request(phone, order_id, token)
        for phone, order_id in paying:
            self.send_payment_request(phone, order_id)


def _report_numbers(report):
    """The print report's numbers for the order history (task 3.3)."""
    if not report or "error" in report:
        return {}
    return {kind: len(report.get(kind) or []) for kind in ("problems", "warnings", "notes")}


def local_number(phone):
    """The customer's number as Israelis write it, for the Bit request:
    "972501234567" -> "050-123-4567". Other countries stay as they are (+…)."""
    digits = "".join(c for c in phone or "" if c.isdigit())
    if digits.startswith("972") and len(digits) == 12:
        local = "0" + digits[3:]
        return f"{local[:3]}-{local[3:6]}-{local[6:]}"
    return "+" + digits if digits else "?"


# The print tool and the album planner write their notes in English (for the
# Mac's Terminal). The owner reads them in WhatsApp, in Hebrew (owner's test,
# task 1.2b: English mixed into a Hebrew line came out scrambled).
_HEBREW = [
    (re.compile(r"^(cover|page (\d+)): (.+?) prints at only"), "owner_check_blurry"),
    (re.compile(r"^(\d+) pages: the printer needs"), "owner_check_page_count"),
    (re.compile(r"^(\d+) pages: the book must have"), "owner_check_page_count"),
    (re.compile(r"^The customer's cover photo"), "owner_check_cover_replaced"),
    (re.compile(r"^The cover photo .* is shown smaller"), "owner_check_cover_small"),
    (re.compile(r"^Only (\d+) usable photos"), "owner_check_few_photos"),
]


def in_hebrew(item, t):
    """One line of the print check, in Hebrew. Unknown lines: a short Hebrew
    pointer to the log (the English text is in bot.log)."""
    for pattern, key in _HEBREW:
        found = pattern.search(item)
        if not found:
            continue
        if key == "owner_check_blurry":
            place = t["preview_cover"] if found.group(1) == "cover" else \
                t["preview_page"].format(page=found.group(2))
            digits = re.findall(r"\d+", found.group(3))   # "007.jpg" -> photo 7, as sent
            photo = str(int(digits[-1])) if digits else _ltr(found.group(3))
            return t[key].format(place=place, photo=photo)
        return t[key].format(count=found.group(1) if found.groups() else "")
    log.info("Print check note: %s", item)
    return t["owner_check_other"]


def _ltr(text):
    """Keep a code or a file name (Latin letters) in one piece inside a Hebrew
    line: WhatsApp otherwise mixes up its place in the sentence."""
    return "\u2066" + str(text) + "\u2069"


def _last_digits(phone):
    """Only the last 3 digits of the customer's number (enough to tell them apart)."""
    return (phone or "?")[-3:]


def _clean(text):
    return " ".join((text or "").split()).strip(" .!?").lower()


def run_print_tool(order_id):
    """Make the album's print files. Returns the tool's report, or {"error": ...}."""
    if not ALBUM_PYTHON.exists():
        return {"error": f"{ALBUM_PYTHON} is missing (album tools not installed)"}
    command = [str(ALBUM_PYTHON), str(PRINT_SCRIPT), "--order", order_id, "--json"]
    try:
        done = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True,
                              text=True, timeout=TOOL_SECONDS)
    except subprocess.TimeoutExpired:
        return {"error": "the print tool took too long"}
    lines = done.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        detail = (done.stderr or done.stdout).strip()[-300:]
        log.error("❌ Print files of %s were not made: %s", short(order_id), detail)
        return {"error": detail.splitlines()[-1] if detail else "unknown"}
