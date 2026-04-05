"""
api/index.py — TeleCMS FileStore Pro
Vercel Serverless Entry Point。
FastAPI app + Lifespan (connect/disconnect) + Webhook endpoint。
"""
import sys
import os

# api/index.py မှ root-level modules import နိုင်ရန် (config, client, ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse

from config import config
from client import get_client, setup_webhook
from database import get_mongo_client
from dispatcher import dispatch_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Lifespan — startup / shutdown
# ════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 TeleCMS FileStore Pro — Starting up...")

    # 1. Config validation
    try:
        config.validate()
        logger.info("✅ Config validated")
    except ValueError as e:
        logger.critical(f"❌ Config error: {e}")
        raise

    # 2. MongoDB ping
    try:
        mongo = get_mongo_client()
        await mongo.admin.command("ping")
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.critical(f"❌ MongoDB error: {e}")
        raise

    # 3. Pyrogram client connect
    try:
        client = await get_client()
        logger.info("✅ Pyrogram connected")
    except Exception as e:
        logger.critical(f"❌ Pyrogram error: {e}")
        raise

    # 4. Register webhook (warn only — don't block startup)
    try:
        result = await setup_webhook()
        if result.get("ok"):
            logger.info(f"✅ Webhook set → {config.WEBHOOK_URL}/webhook")
        else:
            logger.warning(f"⚠️ Webhook response: {result}")
    except Exception as e:
        logger.warning(f"⚠️ Webhook setup warning: {e}")

    logger.info("🎉 Bot is ready!")
    yield  # ── App running ────────────────────────────────────────

    # Shutdown
    logger.info("🛑 Shutting down...")
    try:
        client = await get_client()
        if client.is_connected:
            await client.disconnect()
            logger.info("✅ Pyrogram disconnected")
    except Exception as e:
        logger.warning(f"Shutdown warning: {e}")


# ════════════════════════════════════════════════════════════════
# FastAPI App
# ════════════════════════════════════════════════════════════════

app = FastAPI(
    title="TeleCMS FileStore Pro",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _verify_webhook_secret(request: Request) -> bool:
    """
    X-Telegram-Bot-Api-Secret-Token header စစ်ဆေးသည်。
    WEBHOOK_SECRET မ set မထားရင် skip သည်。
    """
    if not config.WEBHOOK_SECRET:
        return True
    token    = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = hashlib.sha256(config.WEBHOOK_SECRET.encode()).digest()
    received = hashlib.sha256(token.encode()).digest()
    return hmac.compare_digest(expected, received)


# ════════════════════════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "ok", "bot": "TeleCMS FileStore Pro"}


@app.get("/health")
async def health():
    """Health check — MongoDB + Pyrogram status"""
    result: dict[str, Any] = {"status": "ok", "services": {}}

    try:
        mongo = get_mongo_client()
        await mongo.admin.command("ping")
        result["services"]["mongodb"] = "connected"
    except Exception as e:
        result["services"]["mongodb"] = f"error: {e}"
        result["status"] = "degraded"

    try:
        client = await get_client()
        result["services"]["pyrogram"] = (
            "connected" if client.is_connected else "disconnected"
        )
    except Exception as e:
        result["services"]["pyrogram"] = f"error: {e}"
        result["status"] = "degraded"

    http_status = (
        status.HTTP_200_OK
        if result["status"] == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(content=result, status_code=http_status)


@app.post("/webhook")
async def webhook(request: Request):
    """
    Telegram Webhook endpoint。
    Telegram က update POST လုပ်လာတိုင်း ဒီ endpoint ကို ရောက်သည်。
    """
    # 1. Secret token verify
    if not _verify_webhook_secret(request):
        logger.warning("❌ Webhook secret mismatch!")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    # 2. JSON parse
    try:
        update: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return Response(status_code=status.HTTP_200_OK)

    # 3. Log update type
    update_type = next(
        (k for k in ("message", "callback_query", "chat_member", "my_chat_member")
         if k in update),
        "unknown",
    )
    logger.info(f"📨 Update #{update.get('update_id', '?')} | {update_type}")

    # 4. Get client
    try:
        client = await get_client()
    except Exception as e:
        logger.error(f"Client error: {e}")
        return Response(status_code=status.HTTP_200_OK)

    # 5. Dispatch (always return 200 to Telegram regardless of errors)
    try:
        await dispatch_update(client, update)
    except Exception as e:
        logger.exception(f"Dispatch error: {e}")

    return Response(status_code=status.HTTP_200_OK)


@app.post("/setup-webhook")
async def manual_setup_webhook():
    """Manual webhook re-registration (admin use)"""
    try:
        result = await setup_webhook()
        return {
            "status": "ok",
            "webhook_url": f"{config.WEBHOOK_URL}/webhook",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
