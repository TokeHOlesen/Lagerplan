# Lagerplan

Web app that calculates the expected man-hours per working day at the
warehouse, from pick series entered by admins. Django 5.2 (LTS), SQLite,
Gunicorn behind Caddy. The user interface is in Danish.

## How it works

* Admins enter pick series per day (type and number of items) on the
  **Redigér uge** page. That is the only data stored.
* Everything else is calculated when a page is shown: picking, forklift,
  wrapping, booking, labeling, collection (60/30/10 % over the next three
  working days), pallets in storage, storage status and the storage
  surcharge. Editing an earlier day therefore updates later days automatically.
* Working days are Monday to Friday, excluding Danish public holidays (built
  in, including Easter-based ones). Extra closed days go in `rates.toml`.
* All rates and thresholds live in `rates.toml`. Edit the file and the app
  picks up the change within a second; no restart needed. There is no web UI
  for them.

### Storage rules as implemented

Booking takes 0.35 h per 100 pcs for Mixed series and a fixed 0.12 h per
series for all other types (`[task_overrides.booking]` in `rates.toml`).

Hynder (cushions) series count as one piece per series for forklift,
wrapping, booking, labeling and collection, whatever their size. Only picking
(1.2 h per 100 pcs) uses the actual number of pieces. This is set under
`[one_piece_handling]` in `rates.toml`.

Each pick series makes pallets according to its type, set in `rates.toml`:
either per 100 pcs (Mixed 22, DSV 20, Large different 18, Large same 15) or a
fixed number per series regardless of size (Hynder: 1). Capacity is 400
pallets.

Pallets leave on the same 60/30/10 schedule as the items. Because pallets
are collected throughout the day, half of the pallets collected on a day
(`freed_during_day = 0.5`) no longer count toward that day's storage. A day's
storage figure is that day's new pallets, plus earlier pallets not yet
collected, minus half of the pallets collected that day. Example: 100 pallets
picked Monday = 100 on Monday, 70 on Tuesday (100 - 60/2), 25 on Wednesday
(40 - 30/2), 5 on Thursday (10 - 10/2), 0 on Friday.

Occupied share: up to 60 % is good, above 60 % up to 80 % is tight (+10 %),
above 80 % up to 100 % is very tight (+15 %), above 100 % is over capacity
(+20 % and a warning). All thresholds and surcharges are set in `rates.toml`. The surcharge is applied last, to the day's full total including
collection.

## Project layout

```
lagerplan/            Django settings and URLs
workload/
  calculation.py      the calculation rules (pure Python, fully tested)
  calendar_dk.py      working days and Danish holidays
  ratesconfig.py      reads and validates rates.toml
  presentation.py     formats results for the pages (Danish numbers)
  views.py            pages
  templates/          HTML (Danish)
  static/workload/    CSS and a small script for the week editor
  tests/              automated tests
rates.toml            rates, thresholds, extra closed days
deploy/               systemd unit, Caddyfile, backup script
```

## Run it locally

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # DJANGO_DEBUG=1 is fine locally
python manage.py migrate
python manage.py createsuperuser  # your own "owner" account
python manage.py test             # should report all tests OK
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in.

## Roles

* **Ejer** (owner): the superuser you create with `createsuperuser`. Can do
  everything, and other admins cannot edit or reset this account.
* **Administrator**: edits weekly data and manages users (create, deactivate,
  set new passwords). Set by ticking *Administrator* on the user.
* **Læser** (viewer): sees weeks and the calendar only.

There is no outgoing email, so a forgotten password is handled by an admin
setting a new one on the **Brugere** page. Anyone can change their own
password under **Skift adgangskode**.

## Changing the rates

Edit `rates.toml`, then check it:

```sh
python manage.py check_rates
```

It prints the values in use, or the exact error. If the file is invalid, the
running app keeps the last valid rates and logs the error, so a typo can't
take the site down. Changes also apply to past weeks.

## Deploying on Debian

These steps assume the app lives in `/srv/lagerplan` and runs as the system
user `lagerplan`. Replace `lagerplan.example.dk` with your host name, whose
DNS must point at the server (needed for the Let's Encrypt certificate).

```sh
# 1. Packages
sudo apt install python3-venv sqlite3 caddy

# 2. User and code
sudo adduser --system --group --home /srv/lagerplan lagerplan
# Copy the project into /srv/lagerplan (git clone, rsync or unzip), then:
sudo chown -R lagerplan:lagerplan /srv/lagerplan
sudo chmod 755 /srv/lagerplan

# 3. Python environment
cd /srv/lagerplan
sudo -u lagerplan python3 -m venv .venv
sudo -u lagerplan .venv/bin/pip install -r requirements.txt

# 4. Configuration
sudo -u lagerplan cp .env.example .env
sudo -u lagerplan chmod 600 .env
sudo -u lagerplan nano .env
#   DJANGO_DEBUG=0
#   DJANGO_SECRET_KEY=<output of: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
#   DJANGO_ALLOWED_HOSTS=lagerplan.example.dk

# 5. Database, static files, first user
sudo -u lagerplan .venv/bin/python manage.py migrate
sudo -u lagerplan .venv/bin/python manage.py collectstatic --noinput
sudo -u lagerplan .venv/bin/python manage.py createsuperuser
sudo -u lagerplan .venv/bin/python manage.py check --deploy
#   (warnings about SECURE_SSL_REDIRECT and HSTS can be ignored: Caddy redirects to HTTPS)

# 6. App service
sudo cp deploy/lagerplan.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lagerplan
sudo systemctl status lagerplan

# 7. Caddy (HTTPS)
#    Append deploy/Caddyfile to /etc/caddy/Caddyfile with your host name, then:
sudo systemctl reload caddy
```

Logs: `sudo journalctl -u lagerplan -f` (app) and `sudo journalctl -u caddy -f`.

### Updating to a new version

```sh
cd /srv/lagerplan
# copy in the new code (git pull, rsync, ...), keeping .env, db.sqlite3 and rates.toml
sudo -u lagerplan .venv/bin/pip install -r requirements.txt
sudo -u lagerplan .venv/bin/python manage.py migrate
sudo -u lagerplan .venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart lagerplan
```

### Backups

The whole database is one file, `db.sqlite3`. `deploy/backup.sh` makes a
safe copy while the app runs and keeps 30 days. Schedule it with
`sudo crontab -u lagerplan -e`:

```
15 2 * * * /srv/lagerplan/deploy/backup.sh
```

Copy `/srv/lagerplan/backups` off the server regularly as well.
