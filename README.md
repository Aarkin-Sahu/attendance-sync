Attendance Sync
A small personal project that checks my college attendance for me, so I don't have to log in and type an OTP every time I want to know whether I can skip a class.

A scheduled Python job fetches my attendance, saves it as JSON, and a lightweight web page turns it into something I can read on my phone: per-subject percentages, how many classes I can still miss, and a lecture-by-lecture Present/Absent list.

Heads up: this is an unofficial hobby project. It is not affiliated with or endorsed by my college or its portal provider. See Disclaimer.

What it shows
Overall attendance and classes attended out of classes held
Per-subject cards, lowest attendance first, colour-coded:
red: below the 75% target
amber: within 5 points above the target
green: comfortably above it
"You can miss N more classes" or "Attend the next N classes in a row" for each subject, calculated against the 75% target
Lecture list under each subject: date, day, time slot, lecture type, and a green PRESENT or red ABSENT chip
Today card listing today's classes in time order
Stale-data warning if the last sync is older than expected, so you know the job may be failing
The page always shows the last synced data. Attendance only changes a few times a day, so live data wasn't a goal. The goal is planning ahead.

How it works
Two halves that never talk to each other directly:



GitHub Actions (scheduled)            Web page (static)
┌───────────────────────────┐         ┌───────────────────────────┐
│ fetch_attendance.py       │         │ index.html                │
│  1. log in to the portal  │         │  1. download              │
│  2. read the OTP email    │  commit │     attendance.json       │
│  3. fetch attendance and  ├────────►│  2. do the percentage     │
│     per-lecture details   │  JSON   │     and "can miss" maths  │
│  4. write attendance.json │         │  3. draw the cards        │
└───────────────────────────┘         └───────────────────────────┘
sync.yml tells GitHub Actions when to run (times are in UTC).
fetch_attendance.py logs in, picks the OTP out of a Gmail inbox over IMAP, requests the attendance totals and the lecture-level details for each subject, and writes everything to attendance.json with a last_updated timestamp.
The workflow commits attendance.json back to the repo.
index.html reads that file (from raw.githubusercontent.com) and renders the page.
Pressing Refresh on the page only re-reads the saved file. It does not trigger a new sync.

Files
File	Purpose
index.html	The web page (HTML, CSS and JavaScript in one file, no framework)
fetch_attendance.py	Logs in, reads the OTP, fetches attendance and lectures
.github/workflows/sync.yml	Schedule and steps for the sync job
attendance.json	Generated data (do not edit by hand)
Setup
Fork or copy this repo. Keep it public if you want the page to load data from raw.githubusercontent.com.
Edit fetch_attendance.py and fill in the values near the top:
portal username and password
the Gmail address that receives the OTP, plus a Gmail app password (2-Step Verification must be on)
your internal student ID
Point the page at your repo. In index.html, update RAW_URL to your own attendance.json URL.
Run the sync once by hand: Actions → sync-attendance → Run workflow. Check that it finishes green and that attendance.json appears.
Host the page with GitHub Pages: Settings → Pages → Deploy from a branch → main → / (root) → Save. Your page will be at https://<your-username>.github.io/<repo-name>/.
On iPhone: open the link in Safari, tap Share, then Add to Home Screen.
Security note: anyone can read a public repo. If you fork this, don't commit real passwords. Store them in GitHub Actions secrets (Settings → Secrets and variables → Actions) and read them in the script with os.environ.

Schedule
GitHub cron uses UTC. India Standard Time is UTC + 5:30, so convert before editing.

Example: 0 8 * * * runs at 08:00 UTC, which is 1:30 PM IST.

Scheduled runs often start 5 to 15 minutes late, and the sync itself takes one to three minutes because it waits for the OTP email. You can always run it by hand from the Actions tab.

Configuration
At the top of the script in index.html:

Setting	Default	Meaning
TARGET	75	Required attendance percentage
SAFE_MARGIN	5	Within this many points of the target shows amber
STALE_HOURS	5	Show a warning if the data is older than this. Raise it if your schedule has long gaps (for example overnight)
Troubleshooting
Symptom	Likely cause
Yellow "data is old" banner	The sync is delayed or failing. Open the Actions tab and read the log
Workflow fails right away	The Gmail app password is still the placeholder, or the portal login was rejected
Missing IDs in the log	The script couldn't find a student, course or component ID. The log lists the field names it saw
Lectures lists are empty	The lecture request failed or the IDs didn't match. Check the log for Lecture fetch failed
Page shows "Couldn't load attendance"	The repo is private, attendance.json doesn't exist yet, or RAW_URL is wrong
Push fails with a merge conflict	Two runs overlapped. The workflow already queues runs and prefers the newest file
Built with
Python (requests, cryptography, imaplib)
GitHub Actions for scheduling
Plain HTML, CSS and JavaScript for the page
GitHub Pages for hosting
Disclaimer
This is a personal learning project. It logs in with the account holder's own credentials to read their own attendance, and nothing more. It is not an official tool.

Automated logins may be against your college's or portal's rules. Check them before using something like this, and use it at your own risk.
The numbers are only as accurate as the last sync and the data the portal returns. Always confirm important attendance details on the official portal.
Keep the sync frequency low. This project is not meant to put load on the portal.
GitHub Actions has usage terms. Keep the repo a genuine project and don't use it for unrelated work.
Ideas for later
A leave planner that estimates how skipping a day affects each subject, using the timetable and academic calendar
A native iPhone app and home screen widget
Offline caching so the page opens without internet
