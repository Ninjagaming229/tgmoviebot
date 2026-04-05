"""
client.py — TeleCMS FileStore Pro
Pyrogram client singleton — StringSession သုံး။
"""
import logging
import httpx
from pyrogram import Client

from config import config

logger = logging.getLogger(__name__)

_client: Client | None = None


async def get_client() -> Client:
    global _client

    if _client is None or not _client.is_connected:
        logger.info("🔌 Pyrogram client connecting...")

        session = config.STRING_SESSION

        if session:
            # StringSession mode — session_string parameter သုံး (filename မဟုတ်)
            _client = Client(
                name="telecms_bot",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=session,
                no_updates=True,
            )
        else:
            logger.warning("⚠️ STRING_SESSION မရှိ — bot_token mode (local dev only)")
            _client = Client(
                name="telecms_bot",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                bot_token=config.BOT_TOKEN,
                in_memory=True,
                no_updates=True,
            )

        await _client.connect()
        me = await _client.get_me()
        logger.info(f"✅ Connected as @{me.username} (ID: {me.id})")

    return _client


async def setup_webhook() -> dict:
    """Telegram Webhook set လုပ်သည်"""
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
                    "chat_member",
                    "my_chat_member",
                ],
                "drop_pending_updates": False,
            },
        )
        result = resp.json()

    if result.get("ok"):
        logger.info("✅ Webhook set!")
    else:
        logger.error(f"❌ Webhook failed: {result}")

    return result


async def get_bot_info() -> tuple[int, str]:
    client = await get_client()
    me = await client.get_me()
    return me.id, me.username
