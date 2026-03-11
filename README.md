# 🎬 MediaSearchBot

A powerful Telegram media search bot built with **Pyrogram v2**.  
Users send a movie/file name → bot shows paginated results with **Prev / Next** navigation — just like AutoFilterBot.

---

## ✨ Features

| Feature | Description |
|---|---|
| 💬 **Message Search** | Send any name → get file buttons with pagination |
| ◀▶ **Prev / Next** | Browse pages of results |
| 🌐 **Inline Mode** | Search via `@bot query` in any chat |
| 📡 **Auto Index** | New files in watched channels are saved instantly |
| 🛠 **Admin Commands** | `/index`, `/total`, `/delete`, `/channel`, `/logs` |
| 🔒 **Force Subscribe** | Require users to join a channel before searching |

---

## 🚀 Quick Start

### 1. Clone & install
```bash
git clone https://github.com/you/MediaSearchBot
cd MediaSearchBot
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
cp sample.env .env
# Edit .env with your values
```

### 3. Run the bot
```bash
python main.py
```

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_ID` | ✅ | From my.telegram.org |
| `API_HASH` | ✅ | From my.telegram.org |
| `BOT_TOKEN` | ✅ | From @BotFather |
| `DATABASE_URI` | ✅ | MongoDB connection string |
| `ADMINS` | ✅ | Space-separated admin user IDs |
| `CHANNELS` | ✅ | Space-separated channel IDs to watch |
| `DATABASE_NAME` | ❌ | Default: `MediaSearchDB` |
| `COLLECTION_NAME` | ❌ | Default: `Telegram_files` |
| `MAX_RESULTS` | ❌ | Files per page (default: `10`) |
| `AUTH_CHANNEL` | ❌ | Force-join channel ID |
| `LOG_CHANNEL` | ❌ | Channel for bot logs |
| `USERBOT_STRING_SESSION` | ❌ | Required for `/index` command |
| `USE_CAPTION_FILTER` | ❌ | Also search captions (default: `false`) |

---

## 📥 Bulk Index Existing Channels

### Option A – Bot command (while bot is running)
```
/index -100123456789
```

### Option B – Standalone indexer (no bot needed)
```bash
# Index all channels from CHANNELS env var
python index.py

# Index specific channels
python index.py -100123456789 @mychannel

# With options
python index.py --delay 1.0 --limit 500 -100123456789
```

**Options:**
- `--delay N` — seconds between requests (default: `0.5`)
- `--limit N` — max files per channel, `0` = unlimited
- Channels can be numeric IDs (`-100123456789`) or usernames (`@channel`)

### Generate userbot session string
```bash
python generate_session.py
```

---

## 🤖 Bot Commands

| Command | Who | Description |
|---|---|---|
| `/start` | Everyone | Welcome message + search buttons |
| `/total` | Admins | Total files in database |
| `/channel` | Admins | List watched channels |
| `/delete` | Admins | Delete file (reply to media) |
| `/index <channel>` | Admins | Bulk-index a channel |
| `/logs` | Admins | Download log file |

---

## 🔍 Search Tips

- **Plain search:** just type a movie name
- **Filter by type:** `movie name | video` or `song | audio`
- **Inline mode:** `@YourBot movie name` in any chat
- Pagination: use **◀ Prev** and **Next ▶** buttons

---

## 📁 Project Structure

```
MediaSearchBot/
├── main.py              ← Bot entry point
├── config.py            ← All configuration (env vars)
├── index.py             ← Standalone channel indexer
├── generate_session.py  ← Userbot session generator
├── requirements.txt
├── sample.env
├── database/
│   ├── __init__.py
│   └── db.py            ← MongoDB operations (motor)
└── plugins/
    ├── __init__.py
    ├── start.py          ← /start + force-subscribe
    ├── search.py         ← Message search + pagination ◀▶
    ├── inline.py         ← Inline mode search
    ├── channel.py        ← Auto-index new channel posts
    └── admin.py          ← Admin commands
```
