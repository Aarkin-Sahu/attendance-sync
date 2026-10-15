#!/usr/bin/env python3
"""KIET CyberVidya -> attendance.json  (login + OTP from Gmail + attendance).

Fill in the four values below, then run. Saves the server's attendance
response as-is, plus a last_updated timestamp.
"""
import base64, email, imaplib, json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html import unescape

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ======== EDIT THESE FOUR LINES ========
CV_USER = "202501100200005"
CV_PASS = "Aarkin@12345"
GMAIL_USER = "aarkin.25002005@kiet.edu"        # the Gmail that receives the OTP
GMAIL_APP_PASS = "esgg pwlu isoo iovv"
# =======================================

BASE = "https://kiet.cybervidya.net"
KEY = base64.b64decode("NPdLWA5w7yFQhPeUuKmO/A==")   # public values from the site's own JS
IV = base64.b64decode("bV5V6nK4phvQG9ZhkAjugQ==")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(msg):
    print(msg, flush=True)


def encrypt(text):
    p = padding.PKCS7(128).padder()
    data = p.update(text.encode()) + p.finalize()
    e = Cipher(algorithms.AES(KEY), modes.CBC(IV)).encryptor()
    return base64.b64encode(e.update(data) + e.finalize()).decode()


# ---------- OTP from Gmail ----------
def extract_otp(text):
    m = (re.search(r"(?i)(?:otp|one[\s-]*time[\s-]*password|verification code)[^0-9]{0,60}(\d{6})(?!\d)", text)
         or re.search(r"(?<![\w#])(\d{6})(?![\w])", text))
    return m.group(1) if m else None


def message_text(msg):
    parts = [str(make_header(decode_header(msg.get("Subject", ""))))]
    for part in msg.walk():
        if part.get_content_maintype() != "text":
            continue
        raw = part.get_payload(decode=True)
        if raw is None:
            continue
        try:
            text = raw.decode(part.get_content_charset() or "utf-8", "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        if part.get_content_subtype() == "html":
            text = unescape(re.sub(r"<[^>]+>", " ", text))
        parts.append(text)
    return "\n".join(parts)


def otp_in_inbox(since_ts):
    day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d-%b-%Y")
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(GMAIL_USER, GMAIL_APP_PASS.replace(" ", ""))
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, "SINCE", day)
        for mid in reversed((data[0] or b"").split()[-15:]):
            _, got = imap.fetch(mid, "(BODY.PEEK[])")
            if not got or not isinstance(got[0], tuple):
                continue
            msg = email.message_from_bytes(got[0][1])
            try:
                sent = parsedate_to_datetime(msg["Date"]).timestamp()
            except Exception:
                continue
            if sent < since_ts - 30:      # older than this login attempt
                continue
            otp = extract_otp(message_text(msg))
            if otp:
                return otp
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return None


def wait_for_otp(since_ts, timeout=180):
    log("Waiting for OTP email...")
    end = time.time() + timeout
    while time.time() < end:
        otp = otp_in_inbox(since_ts)
        if otp:
            log("OTP found")
            return otp
        time.sleep(6)
    raise RuntimeError("Timed out waiting for OTP email")


# ---------- CyberVidya ----------
def token_of(body):
    d = body.get("data") if isinstance(body.get("data"), dict) else {}
    return body.get("token") or d.get("token") or ""


def login(s):
    user, pw = CV_USER, CV_PASS

    try:   # accounts without OTP get a token straight away
        r = s.post(f"{BASE}/api/auth/login", json={"userName": user, "password": pw}, timeout=30)
        if r.status_code == 400:
            raise RuntimeError("Wrong CyberVidya username or password")
        if r.ok and token_of(r.json()):
            s.login_body = r.json()
            log("Logged in (no OTP needed)")
            return token_of(r.json())
    except (requests.RequestException, ValueError):
        pass

    for attempt in (1, 2):   # OTP flow, one retry if the code is rejected
        t0 = time.time()
        r = s.post(f"{BASE}/api/auth/encrypt/login", timeout=30, json={
            "userName": encrypt(user), "password": encrypt(pw),
            "device": "WEB", "version": None, "reCaptchaToken": None})
        if not r.ok:
            raise RuntimeError(f"Login failed: HTTP {r.status_code}")
        txn = r.json()["data"]["transactionId"]
        log("OTP requested")
        otp = wait_for_otp(t0)
        r = s.post(f"{BASE}/api/auth/verify/otp", timeout=30, json={
            "otp": otp, "transactionId": txn, "device": "WEB", "version": None})
        if r.ok and token_of(r.json()):
            s.login_body = r.json()
            log("Logged in")
            return token_of(r.json())
        log(f"OTP rejected (HTTP {r.status_code}), attempt {attempt}")
        time.sleep(5)
    raise RuntimeError("Could not log in with OTP")


LECTURE_URL = f"{BASE}/api/attendance/schedule/student/course/attendance/percentage"


def find_key(obj, names):
    """First non-null value for any of `names`, searching nested dicts/lists."""
    if isinstance(obj, dict):
        for n in names:
            if obj.get(n) is not None:
                return obj[n]
        for v in obj.values():
            f = find_key(v, names)
            if f is not None:
                return f
    elif isinstance(obj, list):
        for v in obj:
            f = find_key(v, names)
            if f is not None:
                return f
    return None


def add_lectures(s, token, data):
    """Attach a per-lecture list (date, time, status) to every subject component."""
    hdr = {"Authorization": f"GlobalEducation {token}"}
    student_id = find_key(data, ["studentId"]) or find_key(getattr(s, "login_body", {}), ["studentId"])
    for course in data.get("attendanceCourseComponentInfoList") or []:
        for k in course.get("attendanceCourseComponentNameInfoList") or []:
            k["lectures"] = []
            cid = find_key(course, ["courseId"])
            comp = find_key(k, ["courseCompId", "courseComponentId", "componentId"])
            name = f"{course.get('courseName')} / {k.get('componentName')}"
            if not (student_id and cid and comp):
                log(f"Missing IDs for {name}: studentId={student_id} courseId={cid} compId={comp}; "
                    f"course keys={sorted(course)}; component keys={sorted(k)}")
                continue
            try:
                r = s.post(LECTURE_URL, headers=hdr, timeout=30, json={
                    "studentId": student_id, "sessionId": None,
                    "courseId": cid, "courseCompId": comp})
                r.raise_for_status()
                items = r.json().get("data") or []
            except Exception as e:
                log(f"Lecture fetch failed for {name}: {type(e).__name__}: {e}")
                continue
            lectures = [{"date": l.get("planLecDate"), "day": l.get("dayName"),
                         "time": l.get("timeSlot"), "type": l.get("lectureType"),
                         "status": l.get("attendance")}
                        for item in items for l in (item.get("lectureList") or [])]
            lectures.sort(key=lambda x: x["date"] or "", reverse=True)
            k["lectures"] = lectures
            log(f"{name}: {len(lectures)} lectures")


def main():
    if "PUT_YOUR" in GMAIL_APP_PASS:
        raise RuntimeError("Put your Gmail app password in fetch_attendance.py first")
    s = requests.Session()
    s.headers["User-Agent"] = UA
    token = login(s)
    r = s.get(f"{BASE}/api/attendance/course/component/student", timeout=30,
              headers={"Authorization": f"GlobalEducation {token}"})
    r.raise_for_status()
    data = r.json()["data"]
    add_lectures(s, token, data)
    out = {"last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "data": data}
    path = os.environ.get("OUT_FILE", "attendance.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    log("Done: attendance.json written")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FAILED: {type(e).__name__}: {e}")   # old attendance.json stays untouched
        sys.exit(1)
