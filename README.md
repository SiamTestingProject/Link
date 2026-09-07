# OmniArchiver-F2L

OmniArchiver-F2L is a Python Telegram bot that generates HTTP stream and direct-download links for media stored in Telegram channels. It uses MongoDB for metadata and can distribute streaming requests across multiple bot clients.

## Features

- Single-file indexing with `/link`
- Anime and web-series batch indexing with `/batch`
- Direct HTTP download and browser streaming
- MongoDB-backed metadata and usage statistics
- Optional multi-bot worker pool with round-robin streaming
- Admin and allowed-user controls
- HTTP Range support for seeking
- Health endpoints at `/health` and `/ping`
- In-memory Hydrogram sessions: no persistent `.session` SQLite database is required

## Security model

This repository intentionally contains **no Telegram token, API hash, MongoDB password, owner ID, or other deployment secret**.

- Copy `.env.example` to `.env` and put secrets only in `.env` or your hosting provider's environment.
- `.env`, `config.env`, `start.sh`, Hydrogram session files, logs, and local databases are ignored by Git.
- Do not commit a real `.env`.
- If a token, API hash, or database password is exposed in a screenshot, log, commit, issue, or chat, rotate it at the provider. Removing it from the current source tree does not invalidate an already exposed credential.
- `OWNER_ID` has no hard-coded fallback; startup fails closed when required configuration is missing.

## Requirements

- Python 3.11
- MongoDB or MongoDB Atlas
- Telegram API ID and API hash
- Main bot token from BotFather

## Install

```bash
git clone https://github.com/SiamTestingProject/Link.git
cd Link

python -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the regression tests:

```bash
python -m unittest discover -s tests -v
```

## Configuration

Create a private environment file:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in:

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=

MULTI_BOT_TOKENS=""

OWNER_ID=
AUTH_USERS=""
ALLOWED_USER_IDS=""

TELEGRAM_CHANNEL_ID=
SECRET_CODE_LENGTH=24

DATABASE_URL=
DATABASE_NAME=OmniArchiver

BASE_URL=
```

### Variables

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_API_ID` | Yes | API ID from `my.telegram.org` |
| `TELEGRAM_API_HASH` | Yes | API hash from `my.telegram.org` |
| `TELEGRAM_BOT_TOKEN` | Yes | Main BotFather token |
| `TELEGRAM_BOT_USERNAME` | Yes | Main bot username without `@` |
| `MULTI_BOT_TOKENS` | No | Additional BotFather tokens, separated by spaces or commas |
| `OWNER_ID` | Yes | Numeric Telegram user ID of the owner |
| `AUTH_USERS` | No | Additional admin IDs, separated by spaces or commas |
| `ALLOWED_USER_IDS` | No | User allow-list; empty means everyone may use normal commands |
| `TELEGRAM_CHANNEL_ID` | No | Storage/bin channel ID for direct DM uploads |
| `SECRET_CODE_LENGTH` | No | Generated code length; default `24`, minimum `8` |
| `DATABASE_URL` | Yes | Exact MongoDB connection URI |
| `DATABASE_NAME` | No | MongoDB database name; default `OmniArchiver` |
| `BASE_URL` | Yes | Public HTTP/HTTPS origin used in generated links |
| `BIND_ADDRESS` | No | Optional local override. On Alwaysdata, leave it unset |
| `PORT` | No | Optional local override. On Alwaysdata, leave it unset |

Hosting-provider environment variables take precedence over `.env`, `config.env`, and `start.sh`.

### Worker bots

Put every additional token on one quoted line:

```env
MULTI_BOT_TOKENS="TOKEN_1 TOKEN_2 TOKEN_3 TOKEN_4 TOKEN_5"
```

Five **unique** extra tokens produce six total clients: one primary bot plus five workers. Duplicate tokens are de-duplicated. Invalid or revoked worker tokens are rejected by Telegram and excluded from the active pool.

Every worker bot that is expected to stream channel media must be able to access the relevant Telegram channel.

On low-memory hosting, add workers gradually. Every worker consumes additional RAM and network resources.

## MongoDB Atlas

Use the exact connection string shown by MongoDB Atlas under **Connect → Drivers**. Do not invent or rename the SRV hostname.

If startup reports an error similar to:

```text
The DNS query name does not exist: _mongodb._tcp....
```

the hostname in `DATABASE_URL` is wrong or no longer exists.

Also verify:

- the Atlas database user exists;
- its password is correct;
- Atlas Network Access allows the hosting server to connect;
- special characters in a URI password are URL-encoded.

## Alwaysdata deployment

The steps below match an Alwaysdata **Public Cloud / Free** deployment.

### 1. Select Python 3.11

In Alwaysdata:

**Environment → Python → 3.11**

Reconnect SSH after changing the Python version and verify:

```bash
python --version
```

### 2. Connect over SSH

```bash
ssh <account>@ssh-<account>.alwaysdata.net
```

### 3. Clone and install

```bash
cd ~
git clone https://github.com/SiamTestingProject/Link.git
cd Link

python -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Optionally remove pip's download cache afterward:

```bash
python -m pip cache purge
```

### 4. Create `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

For Alwaysdata Free, set:

```env
BASE_URL=https://<account>.alwaysdata.net
```

Do **not** set `BIND_ADDRESS` or `PORT` in `.env` for an Alwaysdata User Program site. Alwaysdata supplies its own `IP` and `PORT`, and the application uses those provider values.

### 5. Optional one-time cleanup after upgrading from an older build

Older releases used file-backed Hydrogram SQLite sessions. This release uses in-memory bot sessions, which avoids `sqlite3.DatabaseError: database disk image is malformed`.

First make sure no old SSH test process or old Alwaysdata site instance is still running. Then remove old app-owned session databases:

```bash
cd ~/Link
rm -f bot_main.session* worker_*.session*
```

The new build will not recreate these session files.

### 6. Test once from SSH

```bash
cd ~/Link
source venv/bin/activate
python -m bot
```

Confirm MongoDB and Telegram start successfully, then stop the test with:

```text
Ctrl+C
```

Do not leave the bot running permanently from SSH.

### 7. Configure the Alwaysdata site

Go to:

**Web → Sites**

Edit the site for:

```text
<account>.alwaysdata.net
```

Set:

```text
Type:
User program
```

Command:

```text
/home/<account>/Link/venv/bin/python -m bot
```

Working directory:

```text
/home/<account>/Link
```

Environment:

```text
leave empty when using /home/<account>/Link/.env
```

Submit the site configuration.

Do not run another copy under **Advanced → Services** at the same time. Use one deployment instance only.

### 8. Verify

Open:

```text
https://<account>.alwaysdata.net/health
```

Expected response:

```text
OK
```

Also test:

```text
https://<account>.alwaysdata.net/ping
```

The root URL redirects to the configured Telegram bot.

### 9. Logs

Alwaysdata site logs are under:

```bash
cd ~/admin/logs/sites
ls -lt
```

The application log is:

```bash
tail -n 100 ~/Link/event-log.txt
```

### Alwaysdata Free custom-domain restriction

The Alwaysdata Free subscription does not allow a website to be assigned your own domain. Keep:

```env
BASE_URL=https://<account>.alwaysdata.net
```

on the Free plan.

If Alwaysdata shows:

```text
Your subscription Free ... does not allow you to have a website with your own domain
```

that is a plan restriction, not a DNS or application error. A paid Alwaysdata plan is required to add the custom hostname directly to the site.

## Updating an Alwaysdata deployment

Stop/restart through the Alwaysdata site controls rather than leaving an SSH process running.

```bash
cd ~/Link
git pull --ff-only

source venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Then restart the site from **Web → Sites**.

If this is the first update from a file-backed-session version, also run once while the bot is stopped:

```bash
rm -f bot_main.session* worker_*.session*
```

## Common Alwaysdata problems

### Generic `Not Found` page

If `/health` shows the hosting platform's generic 404 page instead of `OK`, the hostname is not mapped to the OmniArchiver User Program site. Check **Web → Sites**.

### `ACCESS_TOKEN_INVALID`

A worker token is invalid or revoked. Generate/copy the correct token from BotFather and restart. Failed workers are excluded automatically.

### Fewer workers than expected

`MULTI_BOT_TOKENS` is split on spaces/commas and duplicates are removed. With five unique extra tokens, startup should report six total clients.

### `database disk image is malformed`

Pull the current version, stop all old bot processes, remove legacy sessions:

```bash
rm -f bot_main.session* worker_*.session*
```

The current code uses `in_memory=True` for all Hydrogram bot clients, so persistent session corruption should no longer recur.

### MongoDB SRV/DNS error

Copy the exact current Atlas Drivers URI and verify the cluster hostname and network access.

## Local run

Set `BASE_URL` to the URL clients can actually reach. If testing only on the same machine, you may additionally set:

```env
BIND_ADDRESS=127.0.0.1
PORT=8080
BASE_URL=http://127.0.0.1:8080
```

Then:

```bash
python -m bot
```

## Docker

```bash
docker build -t omniarchiver-f2l .
docker run --env-file .env -p 8080:8080 omniarchiver-f2l
```

For Docker, set `BIND_ADDRESS=0.0.0.0`, `PORT=8080`, and a `BASE_URL` that external clients can reach.

## Main commands

```text
/start
/help
/privacy
/link <Telegram message link>
/batch anime <first message link> <last message link>
/batch series <first message link> <last message link>
/stats
/log
```

Admin-only operations are protected by the configured owner/admin IDs.
