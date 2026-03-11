#!/usr/bin/env python3
"""
index.py  –  Standalone channel indexer
============================================================
Run this script once to bulk-index existing media files from
one or more Telegram channels/groups into MongoDB.

Requirements:
  • All env vars from config.py must be set
  • USERBOT_STRING_SESSION must be set (user account session)

Usage:
  python index.py                          # indexes all CHANNELS from config
  python index.py -100123456 @mychannel   # indexes specific channels

Options:
  --delay N    seconds to wait between messages (default: 0.5)
  --limit N    stop after N files per channel  (default: unlimited)
  --resume     skip files already in DB (default: True)
  --no-resume  re-check even duplicates
============================================================
"""

import asyncio
import logging
import sys
import argparse
import re
from datetime import datetime

# ── Setup logging before importing anything else ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("indexer")
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ── Imports (after path is set up) ────────────────────────────────────────────
from pyrogram import Client
from pyrogram.errors import FloodWait, ChannelInvalid, PeerIdInvalid

from config import (
    API_ID, API_HASH, BOT_TOKEN, SESSION,
    USERBOT_STRING, CHANNELS,
)
from database.db import Media, save_file


# ─────────────────────────────────────────────────────────────────────────────
#  Progress helper
# ─────────────────────────────────────────────────────────────────────────────

class Progress:
    def __init__(self, channel_name: str):
        self.channel  = channel_name
        self.checked  = 0
        self.saved    = 0
        self.skipped  = 0
        self.start_ts = datetime.now()

    def tick(self, saved: bool):
        self.checked += 1
        if saved:
            self.saved += 1
        else:
            self.skipped += 1

    def elapsed(self) -> str:
        delta = datetime.now() - self.start_ts
        m, s  = divmod(int(delta.total_seconds()), 60)
        return f"{m:02d}:{s:02d}"

    def summary(self) -> str:
        return (
            f"  ✅  {self.channel}\n"
            f"      checked={self.checked}  saved={self.saved}  "
            f"duplicates={self.skipped}  time={self.elapsed()}"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Core indexer
# ─────────────────────────────────────────────────────────────────────────────

async def index_channel(
    userbot: Client,
    bot: Client,
    chat,
    delay: float = 0.5,
    limit: int = 0,
) -> Progress:
    """
    Iterate over chat history and save every media file.

    Parameters
    ----------
    userbot : Client  – user account (for get_chat_history)
    bot     : Client  – bot account   (for get_messages to get file_id)
    chat    : int|str – channel id or username
    delay   : float   – sleep between messages to avoid flood
    limit   : int     – 0 = unlimited
    """
    try:
        chat_obj = await userbot.get_chat(chat)
        name = getattr(chat_obj, "title", None) or getattr(chat_obj, "username", str(chat))
    except (ChannelInvalid, PeerIdInvalid) as e:
        logger.error("Cannot access chat %s: %s", chat, e)
        return Progress(str(chat))

    prog = Progress(name)
    logger.info("▶  Indexing: %s  (id=%s)", name, chat)

    async for user_msg in userbot.get_chat_history(chat):
        if limit and prog.checked >= limit:
            logger.info("   Reached limit of %d for %s", limit, name)
            break

        # Retrieve via bot to ensure fresh file_id
        try:
            msg = await bot.get_messages(chat, user_msg.id, replies=0)
        except FloodWait as e:
            logger.warning("FloodWait %ds – sleeping…", e.value)
            await asyncio.sleep(e.value + 1)
            try:
                msg = await bot.get_messages(chat, user_msg.id, replies=0)
            except Exception:
                continue
        except Exception:
            continue

        # Check for media
        for ftype in ("document", "video", "audio"):
            media = getattr(msg, ftype, None)
            if media:
                media.file_type = ftype
                media.caption   = msg.caption
                saved = await save_file(media)
                prog.tick(saved)
                if prog.checked % 50 == 0:
                    logger.info(
                        "   [%s] checked=%d  saved=%d  skipped=%d",
                        name, prog.checked, prog.saved, prog.skipped
                    )
                break

        if delay > 0:
            await asyncio.sleep(delay)

    logger.info(prog.summary())
    return prog


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

async def main(targets: list, delay: float, limit: int):
    if not USERBOT_STRING:
        logger.error(
            "USERBOT_STRING_SESSION is not set.\n"
            "Generate a session string by running:  python generate_session.py"
        )
        sys.exit(1)

    # Ensure DB indexes
    await Media.ensure_indexes()

    userbot = Client(
        "indexer_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=USERBOT_STRING,
        in_memory=True,
    )
    bot = Client(
        "indexer_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    total_saved   = 0
    total_checked = 0
    results       = []

    logger.info("=" * 60)
    logger.info("  MediaSearchBot  –  Standalone Channel Indexer")
    logger.info("  Channels to index: %d", len(targets))
    logger.info("  Delay: %.1fs  |  Limit: %s", delay, limit or "unlimited")
    logger.info("=" * 60)

    async with userbot, bot:
        for chat in targets:
            prog = await index_channel(userbot, bot, chat, delay=delay, limit=limit)
            results.append(prog)
            total_saved   += prog.saved
            total_checked += prog.checked

    # Final report
    logger.info("")
    logger.info("=" * 60)
    logger.info("  INDEXING COMPLETE")
    logger.info("  Total checked : %d", total_checked)
    logger.info("  Total saved   : %d", total_saved)
    logger.info("  Duplicates    : %d", total_checked - total_saved)
    logger.info("=" * 60)
    for p in results:
        logger.info(p.summary())


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk-index Telegram channels into MediaSearchBot database"
    )
    parser.add_argument(
        "channels",
        nargs="*",
        help="Channel IDs or usernames. Defaults to CHANNELS from config.",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between messages (default: 0.5)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max files per channel, 0 = unlimited (default: 0)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    id_re = re.compile(r"^-?\d+$")
    raw   = args.channels or [str(c) for c in CHANNELS]
    if not raw:
        logger.error("No channels specified and CHANNELS env var is empty.")
        sys.exit(1)

    targets = [int(c) if id_re.match(c) else c for c in raw]

    asyncio.run(main(targets, delay=args.delay, limit=args.limit))
