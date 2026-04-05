"""
database.py — TeleCMS FileStore Pro
Motor (async MongoDB) ဖြင့် data operations များကို handle လုပ်သည်。
"""
import logging
from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId

from config import config

logger = logging.getLogger(__name__)

# Global DB connection — serverless warm instance တွင် persist
_mongo_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    """
    MongoDB Motor client singleton ကို return ဆိုသည်。
    Health check နှင့် lifespan တွင် အသုံးပြုသည်。
    """
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _mongo_client


async def get_db() -> AsyncIOMotorDatabase:
    """Database singleton ကို return ဆိုသည်"""
    global _database
    if _database is None:
        logger.info("🗄️ MongoDB connecting...")
        client = get_mongo_client()
        _database = client[config.DB_NAME]
        logger.info("✅ MongoDB connected!")
    return _database


# ════════════════════════════════════════════════════════════════
# Settings
# ════════════════════════════════════════════════════════════════

async def get_setting(key: str, default=None):
    """Bot setting တစ်ခု ဖတ်သည်"""
    db = await get_db()
    doc = await db.settings.find_one({"key": key})
    return doc["value"] if doc else default


async def set_setting(key: str, value) -> None:
    """Bot setting တစ်ခု သိမ်းသည်"""
    db = await get_db()
    await db.settings.update_one(
        {"key": key},
        {"$set": {"value": value, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


# ════════════════════════════════════════════════════════════════
# Admin State Machine
# ════════════════════════════════════════════════════════════════

async def get_admin_state(user_id: int) -> dict:
    """Admin ၏ current conversation state ဖတ်သည်"""
    db = await get_db()
    doc = await db.admin_states.find_one({"user_id": user_id})
    return doc or {"state": "IDLE", "data": {}}


async def set_admin_state(user_id: int, state: str, data: dict | None = None) -> None:
    """Admin conversation state update လုပ်သည်"""
    db = await get_db()
    await db.admin_states.update_one(
        {"user_id": user_id},
        {"$set": {"state": state, "data": data or {}, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


async def clear_admin_state(user_id: int) -> None:
    """Admin state ကို IDLE reset လုပ်သည်"""
    await set_admin_state(user_id, "IDLE", {})


# ════════════════════════════════════════════════════════════════
# Admin Session
# ════════════════════════════════════════════════════════════════

async def is_admin_logged_in(user_id: int) -> bool:
    """Admin login ဝင်ထားသလား စစ်သည်"""
    db = await get_db()
    doc = await db.admin_sessions.find_one({"user_id": user_id, "active": True})
    return doc is not None


async def set_admin_session(user_id: int, active: bool) -> None:
    """Admin session set/clear လုပ်သည်"""
    db = await get_db()
    await db.admin_sessions.update_one(
        {"user_id": user_id},
        {"$set": {"active": active, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


# ════════════════════════════════════════════════════════════════
# Storage Channels
# ════════════════════════════════════════════════════════════════

async def add_storage_channel(
    channel_id: int, channel_name: str, invite_link: str | None = None
) -> None:
    """Private storage channel ထည့်သည်"""
    db = await get_db()
    await db.storage_channels.update_one(
        {"channel_id": channel_id},
        {"$set": {"channel_name": channel_name, "invite_link": invite_link,
                  "added_at": datetime.utcnow()}},
        upsert=True,
    )


async def remove_storage_channel(channel_id: int) -> None:
    """Storage channel ဖျက်သည်"""
    db = await get_db()
    await db.storage_channels.delete_one({"channel_id": channel_id})


async def get_storage_channels() -> list:
    """Storage channels အားလုံး ဖတ်သည်"""
    db = await get_db()
    return await db.storage_channels.find().to_list(100)


# ════════════════════════════════════════════════════════════════
# ForceSub Channels
# ════════════════════════════════════════════════════════════════

async def add_forcesub_channel(
    channel_id: int,
    channel_name: str,
    channel_username: str | None = None,
    invite_link: str | None = None,
) -> None:
    """ForceSub channel ထည့်သည်"""
    db = await get_db()
    await db.forcesub_channels.update_one(
        {"channel_id": channel_id},
        {"$set": {"channel_name": channel_name, "channel_username": channel_username,
                  "invite_link": invite_link, "added_at": datetime.utcnow()}},
        upsert=True,
    )


async def remove_forcesub_channel(channel_id: int) -> None:
    """ForceSub channel ဖျက်သည်"""
    db = await get_db()
    await db.forcesub_channels.delete_one({"channel_id": channel_id})


async def get_forcesub_channels() -> list:
    """ForceSub channels အားလုံး ဖတ်သည်"""
    db = await get_db()
    return await db.forcesub_channels.find().to_list(50)


# ════════════════════════════════════════════════════════════════
# Content Management
# ════════════════════════════════════════════════════════════════

async def create_content(content_data: dict) -> str:
    """Content အသစ် (movie/series) DB ထဲ သိမ်းသည်"""
    db = await get_db()
    content_data["created_at"] = datetime.utcnow()
    content_data["updated_at"] = datetime.utcnow()
    result = await db.content.insert_one(content_data)
    return str(result.inserted_id)


async def get_content(content_id: str) -> Optional[dict]:
    """Content ID ဖြင့် content ရှာသည်"""
    db = await get_db()
    # ObjectId ဖြင့် ရှာသည်
    try:
        doc = await db.content.find_one({"_id": ObjectId(content_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
    except Exception:
        pass
    # content_hash ဖြင့် ရှာသည် (fallback)
    doc = await db.content.find_one({"content_hash": content_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def update_content(content_id: str, update_data: dict) -> None:
    """Content update လုပ်သည်"""
    db = await get_db()
    update_data["updated_at"] = datetime.utcnow()
    await db.content.update_one(
        {"_id": ObjectId(content_id)},
        {"$set": update_data},
    )


async def delete_content(content_id: str) -> None:
    """Content ဖျက်သည်"""
    db = await get_db()
    await db.content.delete_one({"_id": ObjectId(content_id)})


async def get_all_content(
    content_type: str | None = None, limit: int = 10, skip: int = 0
) -> list:
    """Content list paginated ဖြင့် ဖတ်သည်"""
    db = await get_db()
    query = {"type": content_type} if content_type else {}
    cursor = db.content.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def count_content(content_type: str | None = None) -> int:
    """Content အရေအတွက် ရေတွက်သည်"""
    db = await get_db()
    query = {"type": content_type} if content_type else {}
    return await db.content.count_documents(query)


# ════════════════════════════════════════════════════════════════
# Posts
# ════════════════════════════════════════════════════════════════

async def create_post(content_id: str, channel_id: int, message_id: int) -> None:
    """Channel post record သိမ်းသည်"""
    db = await get_db()
    await db.posts.insert_one({
        "content_id": content_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "created_at": datetime.utcnow(),
    })


# ════════════════════════════════════════════════════════════════
# User Messages (Auto-Delete)
# ════════════════════════════════════════════════════════════════

async def save_user_messages(
    user_id: int, forcesub_channel_id: int, message_ids: list[int]
) -> None:
    """
    User ထံ ပေးပို့ထားသော message IDs သိမ်းသည်。
    ForceSub channel မှ ထွက်လျှင် ဖျက်နိုင်ရန်。
    """
    if not message_ids:
        return
    db = await get_db()
    await db.user_messages.insert_one({
        "user_id": user_id,
        "forcesub_channel_id": forcesub_channel_id,
        "message_ids": message_ids,
        "created_at": datetime.utcnow(),
    })


async def get_user_messages_by_channel(
    user_id: int, forcesub_channel_id: int
) -> list[int]:
    """User ၏ channel-specific message IDs ဖတ်သည်"""
    db = await get_db()
    docs = await db.user_messages.find(
        {"user_id": user_id, "forcesub_channel_id": forcesub_channel_id}
    ).to_list(200)
    all_ids: list[int] = []
    for doc in docs:
        all_ids.extend(doc.get("message_ids", []))
    return all_ids


async def delete_user_messages_record(
    user_id: int, forcesub_channel_id: int
) -> None:
    """User message records DB မှ ဖျက်သည်"""
    db = await get_db()
    await db.user_messages.delete_many(
        {"user_id": user_id, "forcesub_channel_id": forcesub_channel_id}
    )
