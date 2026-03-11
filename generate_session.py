#!/usr/bin/env python3
"""
generate_session.py  –  Generate a Pyrogram user-account session string.
Run this once and put the output in USERBOT_STRING_SESSION env var.

Usage:
  python generate_session.py
"""

import asyncio
from pyrogram import Client
from config import API_ID, API_HASH


async def main():
    print("=" * 50)
    print("  Pyrogram Session String Generator")
    print("=" * 50)
    print("You will be asked to log in with your Telegram account.")
    print("This is required for the /index command (userbot).\n")

    async with Client(":memory:", api_id=API_ID, api_hash=API_HASH) as client:
        session_string = await client.export_session_string()

    print("\n" + "=" * 50)
    print("  Your USERBOT_STRING_SESSION:")
    print("=" * 50)
    print(session_string)
    print("=" * 50)
    print("\nSet this as the USERBOT_STRING_SESSION environment variable.")


if __name__ == "__main__":
    asyncio.run(main())
