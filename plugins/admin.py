"""
plugins/admin.py  –  Admin-only commands
"""

import os
import logging
import asyncio

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import ADMINS, CHANNELS, USERBOT_STRING, API_ID, API_HASH
from database.db import Media, save_file

logger = logging.getLogger(__name__)
_index_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
#  /total  –  number of files in DB
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("total") & filters.user(ADMINS))
async def total_files(bot: Client, message: Message):
    msg = await message.reply("⏳ Counting…")
    try:
        n = await Media.count_documents()
        await msg.edit(f"📦 <b>Total files in database:</b> <code>{n}</code>")
    except Exception as e:
        await msg.edit(f"Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  /channel  –  list indexed channels
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("channel") & filters.user(ADMINS))
async def channel_info(bot: Client, message: Message):
    if not CHANNELS:
        await message.reply("No channels configured in <code>CHANNELS</code> env var.")
        return

    lines = ["📑 <b>Watched Channels</b>\n"]
    for ch in CHANNELS:
        try:
            chat = await bot.get_chat(ch)
            name = "@" + chat.username if chat.username else (chat.title or str(ch))
        except Exception:
            name = str(ch)
        lines.append(f"• {name}")

    lines.append(f"\n<b>Total:</b> {len(CHANNELS)}")
    text = "\n".join(lines)

    if len(text) < 4096:
        await message.reply(text)
    else:
        path = "/tmp/channels.txt"
        with open(path, "w") as f:
            f.write(text)
        await message.reply_document(path, caption="Indexed channels list")
        os.remove(path)


# ─────────────────────────────────────────────────────────────────────────────
#  /delete  –  remove a file from DB (reply to the file)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_file_cmd(bot: Client, message: Message):
    reply = message.reply_to_message
    if not (reply and reply.media):
        await message.reply("⚠️ Reply to a media file with /delete to remove it from DB.")
        return

    msg = await message.reply("⏳ Processing…")

    for ftype in ("document", "video", "audio"):
        media = getattr(reply, ftype, None)
        if media:
            result = await Media.delete_one({
                "file_name": media.file_name,
                "file_size": media.file_size,
                "file_type": ftype,
            })
            if result.deleted_count:
                await msg.edit("✅ File removed from database.")
            else:
                await msg.edit("❌ File not found in database.")
            return

    await msg.edit("⚠️ Unsupported file type.")


# ─────────────────────────────────────────────────────────────────────────────
#  /logs  –  send log file
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["logs", "logger"]) & filters.user(ADMINS))
async def send_logs(bot: Client, message: Message):
    try:
        await message.reply_document("TelegramBot.log")
    except FileNotFoundError:
        await message.reply("No log file found.")
    except Exception as e:
        await message.reply(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  /index  –  index a channel via userbot
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["index", "indexfiles"]) & filters.user(ADMINS))
async def index_channel_cmd(bot: Client, message: Message):
    """
    Usage: /index -100123456789  [another_channel_id ...]
    Requires USERBOT_STRING_SESSION env var.
    """
    if not USERBOT_STRING:
        await message.reply(
            "⚠️ Set <code>USERBOT_STRING_SESSION</code> env var to use /index.\n\n"
            "Generate one with <code>python generate_session.py</code>"
        )
        return

    if len(message.command) < 2:
        await message.reply(
            "Usage: <code>/index -10012345678</code>\n\n"
            "You can also pass multiple IDs separated by spaces."
        )
        return

    if _index_lock.locked():
        await message.reply("⏳ Another indexing job is already running. Please wait.")
        return

    raw_chats = message.command[1:]
    chats = []
    for c in raw_chats:
        try:
            chats.append(int(c))
        except ValueError:
            chats.append(c)

    msg = await message.reply(f"⏳ Starting indexer for <b>{len(chats)}</b> channel(s)…")
    total_saved = 0
    total_checked = 0

    async with _index_lock:
        try:
            from pyrogram import Client as PyroClient
            userbot = PyroClient(
                "userbot_session",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=USERBOT_STRING,
                in_memory=True,
            )
            async with userbot:
                for chat in chats:
                    try:
                        chat_obj = await userbot.get_chat(chat)
                        chat_name = getattr(chat_obj, "title", str(chat))
                    except Exception:
                        chat_name = str(chat)

                    await msg.edit(
                        f"⏳ Indexing <b>{chat_name}</b>…\n"
                        f"Checked: <code>{total_checked}</code> | "
                        f"Saved: <code>{total_saved}</code>"
                    )

                    async for um in userbot.get_chat_history(chat):
                        try:
                            m = await bot.get_messages(chat, um.id, replies=0)
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                            m = await bot.get_messages(chat, um.id, replies=0)
                        except Exception:
                            continue

                        for ftype in ("document", "video", "audio"):
                            media = getattr(m, ftype, None)
                            if media:
                                media.file_type = ftype
                                media.caption   = m.caption
                                if await save_file(media):
                                    total_saved += 1
                                total_checked += 1
                                break

        except Exception as e:
            logger.exception("Indexing error: %s", e)
            await msg.edit(f"❌ Error during indexing:\n<code>{e}</code>")
            return

    await msg.edit(
        f"✅ <b>Indexing complete!</b>\n\n"
        f"📋 Checked: <code>{total_checked}</code>\n"
        f"💾 New files saved: <code>{total_saved}</code>"
    )
