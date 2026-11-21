"""Tests for the emailed-code reader: made-up mails and a fake mailbox, no network.

Run:  python tests/test_otp_mail.py
"""
import imaplib
import os
import sys
from datetime import datetime, timedelta
from email import message_from_bytes
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import otp_mail  # noqa: E402

SENDER = "VFS Global <donotreply@vfshelpline.com>"


def mail(subject: str, body: str, html: bool = False) -> bytes:
    m = EmailMessage()
    m["From"], m["Subject"] = SENDER, subject
    m.set_content(body, subtype="html" if html else "plain")
    return m.as_bytes()


class FakeMailbox:
    """Just enough of imaplib for otp_mail: mails = [(uid, when, raw, sender)]."""

    def __init__(self, mails, arrives_later=None):
        self.mails, self.later, self.looks, self.calls = list(mails), arrives_later, 0, []

    def noop(self):
        self.looks += 1
        if self.later and self.looks == 3:
            self.mails.append(self.later)

    def uid(self, cmd, *args):
        self.calls.append((cmd,) + args)
        if cmd == "SEARCH":
            want = args[-1].strip('"').lower()
            return "OK", [b" ".join(str(u).encode() for u, _, _, s in self.mails if want in s.lower())]
        u = int(args[0])
        _, when, raw, _ = next(m for m in self.mails if m[0] == u)
        head = f"{u} (UID {u} INTERNALDATE {imaplib.Time2Internaldate(when.timestamp())} BODY[] {{{len(raw)}}}".encode()
        return "OK", [(head, raw), b")"]

    def logout(self):
        self.calls.append(("LOGOUT",))


def setup():
    os.environ.update(OTP_IMAP_USER="tester@example.test", OTP_IMAP_PASSWORD="abcd efgh ijkl mnop")
    otp_mail.dotenv_values = lambda path: {}


def test_code_is_found_in_the_usual_wordings():
    assert otp_mail.extract_code("Your One Time Password (OTP) for VFS login is 483920. Valid for 3 minutes.") == "483920"
    assert otp_mail.extract_code("OTP: 5519 valid till 17:30 on 20-11-2026") == "5519"
    assert otp_mail.extract_code("VFS Global 2026. Your verification code is 771203") == "771203"
    assert otp_mail.extract_code("Use 120934 to continue") == "120934"


def test_dates_times_and_phone_numbers_are_not_codes():
    assert otp_mail.extract_code("Your appointment is on 20-11-2026 at 17:30, ref 2026/11/20") is None
    assert otp_mail.extract_code("Call 02134567890 for help") is None


def test_html_mail_is_read():
    raw = mail("One Time Password", "<html><style>.a{width:600px}</style><p>Your OTP is <b>904417</b></p></html>", html=True)
    assert otp_mail.extract_code(otp_mail.message_text(message_from_bytes(raw))) == "904417"


def test_only_the_new_code_from_the_portal_is_returned():
    setup()
    now = datetime.now().replace(microsecond=0)
    old = (1, now - timedelta(minutes=31), mail("One Time Password", "Your OTP is 111111"), SENDER)
    bank = (2, now + timedelta(seconds=5), mail("Your bank code", "Your OTP is 999999"), "alerts@bank.example")
    new = (3, now + timedelta(seconds=8), mail("One Time Password", "Your OTP is 222222"), SENDER)
    said, box = [], FakeMailbox([old, bank], arrives_later=new)
    assert otp_mail.fetch_code(now, wait_s=5, every_s=0.01, say=said.append, opener=lambda cfg: box) == "222222"
    assert not any("222222" in line for line in said)                       # the code is never logged
    assert all(c[0] in ("SEARCH", "FETCH", "LOGOUT") for c in box.calls)    # read-only
    assert any("PEEK" in str(c) for c in box.calls) and box.calls[-1] == ("LOGOUT",)
    box = FakeMailbox([old, bank])
    assert otp_mail.fetch_code(now, wait_s=0.2, every_s=0.05, opener=lambda cfg: box) is None  # never an old code


def test_mailbox_problems_give_none_with_a_reason():
    setup()
    said = []

    def refuse(cfg):
        raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
    assert otp_mail.fetch_code(datetime.now(), say=said.append, opener=refuse) is None
    assert "could not open" in said[-1]
    assert otp_mail.settings()["password"] == "abcdefghijklmnop"            # App Password spaces removed
    del os.environ["OTP_IMAP_PASSWORD"]
    assert otp_mail.settings() is None and otp_mail.fetch_code(datetime.now(), say=said.append) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
