"""
plugins/search.py  –  Message-based search with paginated results

Flow:
  User sends text  ──►  Bot shows file buttons + Prev/Next navigation
  User taps file   ──►  Bot sends the file
  User taps page   ──►  Bot edits message with new page
"""

import logging
import math

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ChatType

from config import MAX_RESULTS, AUTH_CHANNEL, AUTH_USERS
from database.db import get_search_results
from .start import is_subscribed

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(size or 0)
    for u in units[:-1]:
        if s < 1024:
            return f"{s:.1f} {u}"
        s /= 1024
    return f"{s:.1f} TB"


def _build_keyboard(files: list, query: str, offset: int, total: int) -> InlineKeyboardMarkup:
    """
    Build a keyboard with:
      • One button per file (file_name  │  size)
      • Navigation row: [◀ Prev]  [Page X/Y]  [Next ▶]
    """
    rows = []

    for f in files:
        name = f.get("file_name", "Unknown")
        size = _fmt_size(f.get("file_size", 0))
        ftype = (f.get("file_type") or "").capitalize()
        label = f"🎬 {name}  [{size}]" if len(name) <= 48 else f"🎬 {name[:45]}…  [{size}]"
        # callback: send_file#{file_id}
        rows.append([InlineKeyboardButton(label, callback_data=f"send#{f['file_id']}")])

    # Pagination row
    page_size = MAX_RESULTS
    current_page = (offset // page_size) + 1
    total_pages  = max(1, math.ceil(total / page_size))

    nav = []
    if offset > 0:
        prev_offset = max(0, offset - page_size)
        nav.append(InlineKeyboardButton(
            "◀ Prev", callback_data=f"page#{query}#{prev_offset}"
        ))
    nav.append(InlineKeyboardButton(
        f"📄 {current_page}/{total_pages}", callback_data="noop"
    ))
    if total > offset + page_size:
        nav.append(InlineKeyboardButton(
            "Next ▶", callback_data=f"page#{query}#{offset + page_size}"
        ))

    rows.append(nav)
    rows.append([InlineKeyboardButton("🔎 New Search", switch_inline_query_current_chat=query)])
    return InlineKeyboardMarkup(rows)


def _parse_query(text: str):
    """Split 'movie name | video' → (movie name, video) or (movie name, None)."""
    if "|" in text:
        q, ft = text.split("|", 1)
        return q.strip(), ft.strip().lower() or None
    return text.strip(), None


# ─────────────────────────────────────────────────────────────────────────────
#  Message handler – user sends a movie/file name
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.text
    & filters.private
    & ~filters.command(["start", "help", "index", "total", "delete",
                        "channel", "logger", "logs", "broadcast"])
)
async def search_handler(bot: Client, message: Message):
    """Handle any plain text message as a search query."""
    user = message.from_user
    text = message.text.strip()

    if not text:
        return

    # Force-subscribe check
    if not await is_subscribed(bot, user.id):
        channel = await bot.get_chat(AUTH_CHANNEL)
        invite = (
            f"https://t.me/{channel.username}"
            if channel.username
            else await bot.export_chat_invite_link(AUTH_CHANNEL)
        )
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        from config import FORCE_SUB_MSG
        await message.reply(FORCE_SUB_MSG, reply_markup=InlineKeyboardMarkup(buttons))
        return

    query, file_type = _parse_query(text)

    msg = await message.reply("🔍 <b>Searching…</b>")

    files, next_offset = await get_search_results(
        query, file_type=file_type, max_results=MAX_RESULTS, offset=0
    )

    if not files:
        await msg.edit(
            f"❌ <b>No results for</b> <code>{query}</code>\n\n"
            "Try different keywords or check the spelling."
        )
        return

    total = await _count(query, file_type)
    keyboard = _build_keyboard(files, query, 0, total)

    await msg.edit(
        f"🔎 <b>Results for:</b> <code>{query}</code>\n"
        f"📁 <b>Found:</b> <code>{total}</code> file(s)\n\n"
        "👇 <i>Tap a file to receive it:</i>",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Callback – paginate
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^page#"))
async def page_cb(bot: Client, query: CallbackQuery):
    """Handle Prev / Next page callbacks."""
    _, raw_query, raw_offset = query.data.split("#", 2)
    offset     = int(raw_offset)
    q, ft      = _parse_query(raw_query)

    files, _ = await get_search_results(
        q, file_type=ft, max_results=MAX_RESULTS, offset=offset
    )

    if not files:
        await query.answer("No more results!", show_alert=True)
        return

    total    = await _count(q, ft)
    keyboard = _build_keyboard(files, raw_query, offset, total)

    try:
        await query.message.edit_reply_markup(keyboard)
    except MessageNotModified:
        pass
    await query.answer()


# ─────────────────────────────────────────────────────────────────────────────
#  Callback – send file
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^send#"))
async def send_file_cb(bot: Client, query: CallbackQuery):
    """Send the requested file to the user."""
    _, file_id = query.data.split("#", 1)

    await query.answer("📤 Sending…")

    # Look up file details in DB
    from database.db import _col
    doc = await _col.find_one({"file_id": file_id})
    if not doc:
        await query.answer("⚠️ File not found in database.", show_alert=True)
        return

    caption = doc.get("caption") or ""
    ftype   = doc.get("file_type", "document")
    fname   = doc.get("file_name", "file")

    try:
        if ftype == "video":
            await bot.send_video(
                query.message.chat.id,
                video=file_id,
                caption=caption or f"🎬 <b>{fname}</b>",
            )
        elif ftype == "audio":
            await bot.send_audio(
                query.message.chat.id,
                audio=file_id,
                caption=caption or f"🎵 <b>{fname}</b>",
            )
        else:
            await bot.send_document(
                query.message.chat.id,
                document=file_id,
                caption=caption or f"📄 <b>{fname}</b>",
            )
    except FloodWait as e:
        import asyncio
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.exception("Failed to send file: %s", e)
        await query.answer(f"Error: {e}", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
#  No-op callback (page counter button)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(bot: Client, query: CallbackQuery):
    await query.answer()


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helper
# ─────────────────────────────────────────────────────────────────────────────

async def _count(query: str, file_type: str = None) -> int:
    import re
    from database.db import _col
    from config import USE_CAPTION_FILTER

    query = query.strip()
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = r"(\b|[\.+\-_])" + re.escape(query) + r"(\b|[\.+\-_])"
    else:
        raw_pattern = re.escape(query).replace(r"\ ", r".*[\s\.+\-_()\[\]]")

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        return 0

    filt = (
        {"$or": [{"file_name": regex}, {"caption": regex}]}
        if USE_CAPTION_FILTER
        else {"file_name": regex}
    )
    if file_type:
        filt["file_type"] = file_type

    return await _col.count_documents(filt)
