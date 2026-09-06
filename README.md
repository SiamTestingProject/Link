<div align="center"><h1>🌐 OmniArchiver-F2L</h1>
<b>A high-performance Python Telegram bot to generate permanent HTTP Stream & Direct Download links from your Telegram channels without duplicating files, powered by MongoDB and Multi-Bot request distribution.</b>
</div><br>

## **📑 INDEX**

* [**✨ Features**](#features)
* [**⚙️ Installation**](#installation)
* [**📝 Variables**](#variables)
* [**🎮 Commands & Usage**](#commands)
* [**🕹 Deployment**](#deployment)
  * [Alwaysdata Deployment](#d-alwaysdata)
  * [Local Deployment](#d-local)
  * [Docker Deployment](#d-docker)
* [**❤️ Credits**](#credits)

---

<a name="features"></a>

## ✨ Features

- **🚀 Multi-Bot Worker Pool:** Round-robin streaming across healthy bot clients so simultaneous requests can be distributed, with automatic fallback to the primary bot.
- **🗄️ Organized MongoDB Storage:** Neatly partitions data into separate collections (`movies`, `anime`, `webseries`, `direct_files`).
- **🚫 Zero File Duplication:** Directly indexes files from your existing channels without needing a storage bin channel.
- **🎬 `/link` Command:** Generate instant permanent stream & download links for single movies/files from any channel.
- **📺 `/batch` Command:** Batch index full Anime or Web Series seasons by specifying start and end message links.
- **👥 `AUTH_USERS` Permissions:** Multi-admin support allowing designated users full access to manage and index files.
- **⚡ Hardware Accelerated:** Powered by `tgcrypto` and asynchronous chunk streaming (`Quart`/`Uvicorn`).

---

<a name="installation"></a>

## ⚙️ Installation

**1. Clone the repository:**
```bash
git clone https://github.com/WorkerOfArea51/OmniArchiver-F2L.git
cd OmniArchiver-F2L
```

**2. Create a virtual environment & install requirements:**
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

<a name="variables"></a>

## 📝 Variables

Configure these variables in your `.env` file or hosting environment:

Hosting/provider environment variables take precedence over values in local `start.sh`, `.env`, or `config.env` files. `OWNER_ID` has no built-in fallback; startup fails safely if it is missing.

| Variable | Required | Description |
| :--- | :--- | :--- |
| `TELEGRAM_API_ID` | **Yes** | Telegram API ID from [my.telegram.org](https://my.telegram.org) (`int`) |
| `TELEGRAM_API_HASH` | **Yes** | Telegram API Hash from [my.telegram.org](https://my.telegram.org) (`str`) |
| `TELEGRAM_BOT_TOKEN` | **Yes** | Main Telegram bot token from [@BotFather](https://t.me/BotFather) (`str`) |
| `TELEGRAM_BOT_USERNAME` | **Yes** | Bot username without `@` (`str`) |
| `MULTI_BOT_TOKENS` | *Optional* | Additional worker bot tokens (space-separated) for parallel stream acceleration |
| `OWNER_ID` | **Yes** | Your numeric Telegram user ID (`int`) |
| `AUTH_USERS` | *Optional* | Space-separated list of Telegram user IDs with full admin rights |
| `ALLOWED_USER_IDS` | *Optional* | Allowed user IDs (leave empty to allow everyone) |
| `TELEGRAM_CHANNEL_ID` | *Optional* | Storage Channel ID (with `-100` prefix) only if you want direct files sent in private DMs |
| `DATABASE_URL` | **Yes** | MongoDB connection URI (e.g. `mongodb+srv://...` or `mongodb://localhost:27017`) |
| `DATABASE_NAME` | *Optional* | Database name in MongoDB (default: `OmniArchiver`) |
| `BASE_URL` | **Yes** | Public FQDN URL (e.g. `https://<account>.alwaysdata.net`) |
| `BIND_ADDRESS` | *Optional* | Bind address (defaults to Alwaysdata `IP` when provided, otherwise `::`) |
| `PORT` | *Optional* | Port to listen on (default: `8080`) |

---

<a name="commands"></a>

## 🎮 Commands & Usage

### 🎬 Single Movie Indexing (`/link`)
Generate a permanent stream and download link for a movie in your channel:
```text
/link https://t.me/c/1234567890/42
```
*(Or forward a channel post into the bot and reply with `/link`)*

---

### 📺 Anime Batch Indexing (`/batch anime`)
Index an entire season of Anime episodes into the `anime` collection:
```text
/batch anime https://t.me/c/1234567890/10 https://t.me/c/1234567890/22
```

---

### 🍿 Web Series Batch Indexing (`/batch series`)
Index Web Series episodes into the `webseries` collection:
```text
/batch series https://t.me/c/1234567890/50 https://t.me/c/1234567890/60
```

---

### 📊 Other Commands
- `/stats` - View total indexed movies, anime, series, and active bot workers (Admin only).
- `/log` - Download bot event log file (Admin only).
- `/privacy` - View privacy policy.
- `/help` - View command guide.

---

### ✅ Regression tests
After installing the pinned dependencies, run:
```bash
python -m unittest discover -s tests -v
```

---

<a name="deployment"></a>

## 🕹 Deployment

<a name="d-alwaysdata"></a>

### 🌐 Alwaysdata Deployment

1. **SSH into Alwaysdata:**
   ```bash
   ssh <username>@ssh-<username>.alwaysdata.net
   ```
2. **Clone & Setup:**
   ```bash
   cd ~
   git clone https://github.com/WorkerOfArea51/OmniArchiver-F2L.git
   cd OmniArchiver-F2L
   python3.11 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip cache purge
   ```
3. **Create `start.sh`:**
   ```bash
   nano start.sh
   ```
   Add your environment exports and run: `exec python -m bot`
   ```bash
   chmod +x start.sh
   ```
4. **Configure Site in Alwaysdata Dashboard:**
   - **Type:** `User program`
   - **Command:** `/home/<username>/OmniArchiver-F2L/start.sh`
   - **Working directory:** `/home/<username>/OmniArchiver-F2L`

<a name="d-local"></a>

### 💻 Local Run
```bash
python -m bot
```

<a name="d-docker"></a>

### 🐳 Docker
```bash
docker build -t omniarchiver-f2l .
docker run -p 8080:8080 --env-file .env omniarchiver-f2l
```

---

<a name="credits"></a>

## ❤️ Credits

- [**WorkerOfArea51**](https://github.com/WorkerOfArea51): Maintainer of OmniArchiver-F2L.
