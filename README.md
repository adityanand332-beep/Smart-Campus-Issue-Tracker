# Smart Campus Issue Tracker (CampusFix)

## Features
- Student registration/login with hashed passwords
- SQLite database created automatically
- Report issues with location, category, description, priority
- Search and filter issues
- Dashboard counts and recent reports
- My Issues page
- Issue detail and activity history
- Admin status/priority updates, team assignment and progress notes

## Run
Requires Python 3.10+ and internet for initial Flask install.

**Windows:** extract ZIP, open terminal in project folder:
```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Seed admin account
Email: `admin@campus.local`
Password: `Admin@12345`

Change the default password and `SECRET_KEY` before any public deployment. This is a college-project starter, not hardened production software; add CSRF protection, rate limiting, secure cookie settings, HTTPS, backups and logging before deploying publicly.
