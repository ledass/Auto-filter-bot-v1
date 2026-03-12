# 🎬 auto-filter-bot-v1

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Pyrogram-v2-green?style=for-the-badge&logo=telegram&logoColor=white"/>
  <img src="https://img.shields.io/badge/MongoDB-Motor-brightgreen?style=for-the-badge&logo=mongodb&logoColor=white"/>
  <img src="https://img.shields.io/badge/Deploy-Heroku%20%7C%20Render%20%7C%20Koyeb-purple?style=for-the-badge"/>
</p>

<p align="center">
  A powerful Telegram media search bot — search movies and files directly in PM or any group, with paginated results, auto-delete, and deep-link file delivery.
</p>

---

## ✨ Features

| Feature | Description |
|---|---|
| 💬 **PM Search** | Type any name → paginated file buttons → tap to receive instantly |
| 👥 **Group Search** | Results shown in group → tap → redirected to bot PM → file delivered |
| 🔗 **Deep-Link Delivery** | Group buttons use `t.me/bot?start=<file_id>` — no "start bot first" errors |
| ◀▶ **Prev / Next Pages** | AutoFilterBot-style pagination with page counter |
| 🗑 **Auto-Delete** | Files auto-delete after configurable time to avoid copyright issues |
| 📌 **Save Reminder** | Users instructed to forward to Saved Messages before deletion |
| 📡 **Auto Index** | New files posted in watched channels are saved to DB instantly |
| 🛠 **Admin Commands** | `/index`, `/setskip`, `/total`, `/delete`, `/channel`, `/logs` |
| 🌐 **Inline Mode** | Search via `@bot query` in any chat |
| 🔒 **Force Subscribe** | Optionally require users to join a channel before access |
| 🌍 **Always Alive** | Built-in `aiohttp` web server — compatible with Render & Koyeb (no sleep) |

---

## 🖼 Preview

### Group Search
```
User: Kumki

Bot:
  🔎 Results for: Kumki
  📁 Found: 9 file(s)
  👇 Tap a file → you'll be taken to my PM where it will be sent!

  [1.59 GB]- 🎬 -Kumki 2 (2025) Tamil HQ HDRip 1080p HEVC x…
  [1.38 GB]- 🎬 -Kumki 2 (2025) Tamil HQ HDRip 720p x264 (D…
  [904.43 MB]- 🎬 -Kumki 2 (2025) Tamil HQ HDRip 720p HEVC …
  ──────────────────────────────
  [🗂 1/2]   [NEXT ▶]
```

### File Caption in PM
```
🎬 Kumki 2 (2025) Tamil HQ HDRip 1080p HEVC x265.mkv
📦 Size: 1.59 GB
🗂 Type: Video

⚠️ This file will be auto-deleted in 5 minute(s) to avoid copyright issues.
📌 Forward it to your Saved Messages to keep it forever!

[💾 Save to Saved Messages]
```

---

## 🚀 Deploy

### Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

1. Click the button above
2. Fill in the required environment variables
3. Deploy — uses `Procfile` → `worker: python main.py`

### Render / Koyeb
1. Connect your GitHub repo
2. Set **Start Command:** `python main.py`
3. Set **Health Check URL:** `/health`
4. Add all environment variables
5. Deploy — the built-in web server keeps the container alive permanently

### Manual / VPS
```bash
git clone https://github.com/GouthamSER/auto-filter-bot-v1
cd auto-filter-bot-v1
pip install -r requirements.txt
cp sample.env .env
# Edit .env with your values
python main.py
```

---

## ⚙️ Environment Variables

### Required
| Variable | Description |
|---|---|
| `API_ID` | Get from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Get from [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | Get from [@BotFather](https://t.me/BotFather) |
| `DATABASE_URI` | MongoDB connection string (e.g. `mongodb+srv://...`) |
| `ADMINS` | Space-separated Telegram user IDs — e.g. `123456 789012` |
| `CHANNELS` | Space-separated channel IDs the bot watches — e.g. `-100123 -100456` |
| `LOG_CHANNEL` | — | Channel ID for bot startup/log messages |
| `DATABASE_NAME` | `MediaSearchDB` | MongoDB database name |
| `COLLECTION_NAME` | `Telegram_files` | MongoDB collection name |

### Optional
| Variable | Default | Description |
|---|---|---|

| `SESSION` | `MediaSearchBot` | Pyrogram session name |
| `MAX_RESULTS` | `10` | Files shown per page |
| `AUTO_DELETE_TIME` | `300` | Seconds before file is deleted (300 = 5 min) |
| `USE_CAPTION_FILTER` | `false` | Also search inside file captions |
| `AUTH_CHANNEL` | — | Force users to join this channel ID before using bot |
| `PORT` | `8080` | Web server port (auto-set by Render/Koyeb) |

### Custom Messages (Optional)
| Variable | Description |
|---|---|
| `START_MSG` | Custom welcome message. Supports `{mention}`, `{username}`, `{first_name}` |
| `FORCE_SUB_MSG` | Message shown when user hasn't joined `AUTH_CHANNEL` |

---


## 🤖 Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | Everyone | Welcome message + search buttons |
| `/total` | Admins | Total files saved in database |
| `/channel` | Admins | List all watched channels |
| `/delete` | Admins | Reply to media → removes it from DB |
| `/index <channel>` | Admins | Bulk-index a channel (bot-only, no userbot) |
| `/setskip <N>` | Admins | Set message skip offset for indexing |
| `/logs` | Admins | Download the log file |

---

## 🔍 Search Tips

- **Basic:** type any movie or file name
- **Filter by type:** `movie name | video` or `song name | audio`
- **Inline anywhere:** `@YourBot movie name` in any chat
- **Pagination:** tap **◀ PREV** / **NEXT ▶** to browse all results

---

## 📁 Project Structure

```
MediaSearchBot/
├── main.py                 ← Bot entry point + aiohttp web server
├── config.py               ← All configuration via environment variables
├── index.py                ← Standalone channel bulk-indexer
├── generate_session.py     ← (Unused) Userbot session helper
├── requirements.txt
├── Procfile                ← Heroku: worker: python main.py
├── sample.env              ← Example environment variables
│
├── database/
│   ├── __init__.py
│   └── db.py               ← MongoDB motor operations (no umongo)
│
└── plugins/
    ├── __init__.py
    ├── start.py            ← /start + deep-link file delivery + force-subscribe
    ├── search.py           ← PM & group search, pagination, auto-delete
    ├── inline.py           ← Inline mode search
    ├── channel.py          ← Auto-index new files from watched channels
    └── admin.py            ← Admin commands + channel indexer (bot-only)
```

---

## 🛠 Tech Stack

- **[Pyrogram v2](https://github.com/pyrogram/pyrogram)** — Telegram MTProto client
- **[Motor](https://motor.readthedocs.io/)** — Async MongoDB driver
- **[aiohttp](https://docs.aiohttp.org/)** — Async web server (keep-alive for Render/Koyeb)
- **[MongoDB Atlas](https://www.mongodb.com/atlas)** — Cloud database (free tier works)

---

## 👨‍💻 Credits

| Role | Person |
|---|---|
| **Maintainer & Rewritten By** | [GouthamSER](https://github.com/GouthamSER) |
| Original Concept | Media-Search-bot |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/GouthamSER">GouthamSER</a>
</p>
