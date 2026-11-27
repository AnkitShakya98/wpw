import os
import asyncio
import logging
from pyrogram import Client

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)
log = logging.getLogger(__name__)

app = Client(
    "pwbot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ✅ pwbot import — app create ke baad
import bot  # noqa

# handlers count check
try:
    total = sum(len(v) for v in app.dispatcher.groups.values())
    log.info(f"📊 Handlers registered: {total}")
except Exception as e:
    log.error(f"Handler count error: {e}")


async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN:
        return log.error("❌ creds missing")
    async with app:
        me = await app.get_me()
        log.info(f"✅ @{me.username} ({me.id})")
        log.info("📡 Bot running...")
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Stopped")
