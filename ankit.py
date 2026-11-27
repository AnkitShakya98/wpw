import os, asyncio, logging
from pyrogram import Client

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
log = logging.getLogger(__name__)

app = Client("pwbot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

class _M(type):
    def __getattr__(cls, i): return getattr(app, i)
    def __instancecheck__(cls, x): return isinstance(x, Client)

class CP(metaclass=_M): pass

import pyrogram
pyrogram.Client = CP
import pwbot  # noqa

log.info("📦 pwbot loaded")

async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN: return log.error("❌ creds")
    async with app:
        me = await app.get_me()
        log.info(f"✅ @{me.username}")
        await asyncio.Event().wait()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass