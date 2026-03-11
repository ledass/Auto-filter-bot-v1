import logging
import logging.config
import asyncio

from pyrogram import Client
from pyrogram.enums import ParseMode

from config import (
    API_ID, API_HASH, BOT_TOKEN, SESSION, LOG_CHANNEL
)
from database.db import Media

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
            parse_mode=ParseMode.HTML,
        )

    async def start(self):
        await super().start()
        await Media.ensure_indexes()
        me = await self.get_me()
        self.username = "@" + me.username
        self.mention = me.mention
        logger.info(f"✅ {me.first_name} started as {self.username}")

        if LOG_CHANNEL:
            try:
                await self.send_message(
                    LOG_CHANNEL,
                    f"<b>🤖 {me.mention} started!</b>\n"
                    f"<code>Username:</code> {self.username}"
                )
            except Exception as e:
                logger.warning(f"Could not send startup message to log channel: {e}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")


app = Bot()

if __name__ == "__main__":
    app.run()
