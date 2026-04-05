"""
client.py — TeleCMS FileStore Pro
Pyrogram client singleton manager.
Vercel warm instance တွင် connection ကို reuse လုပ်သည်။
"""
import logging
import httpx
from pyrogram import Client

from config import config

logger = logging.getLogger(__name__)

# Global client instance — serverless warm lambda တွင် persist ဖြစ်သည်
_client: Client | None = None


async def get_client() -> Client:
    """
    Pyrogram client singleton ကို return ဆိုသည်။
    Connection မရှိလျှင် / ပြတ်သွားလျှင် reconnect လုပ်သည်။
    """
    global _client

    if _client is None or not _client.is_connected:
        logger.info("🔌 Pyrogram client connecting...")
        _client = Client(
            name="telecms_bot",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,     # RAM ထဲသာ session သိမ်းသည်
            no_updates=True,    # Webhook mode — polling မဟုတ်
        )
        await _client.connect()
        me = await _client.get_me()
        logger.info(f"✅ Connected as @{me.username} (ID: {me.id})")

    return _client


async def setup_webhook() -> dict:
    """
    Telegram Webhook ကို set လုပ်သည်။
    chat_member updates ပါ enable ထားသည် (auto-delete feature အတွက်)。
    WEBHOOK_URL နှင့် WEBHOOK_SECRET ကို config မှ ဖတ်သည်。
    """
    client = await get_client()
    webhook_url = f"{config.WEBHOOK_URL}/webhook"
    logger.info(f"🔗 Setting webhook → {webhook_url}")

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": config.WEBHOOK_SECRET or "",
                "allowed_updates": [
                    "message",
                    "callback_query",
                    "chat_member",      # User leave detect
                    "my_chat_member",   # Bot kick detect
                ],
                "drop_pending_updates": False,
            },
        )
        result = resp.json()

    if result.get("ok"):
        logger.info("✅ Webhook set successfully!")
    else:
        logger.error(f"❌ Webhook setup failed: {result}")

    return result


async def get_bot_info() -> tuple[int, str]:
    """(bot_id, bot_username) tuple ကို return ဆိုသည်"""
    client = await get_client()
    me = await client.get_me()
    return me.id, me.username
