"""
helpers.py — TeleCMS FileStore Pro
ForceSub checking, link parsing, text formatting utilities。
"""
import re
import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, FloodWait

from database import get_forcesub_channels

logger = logging.getLogger(__name__)

STATUS_DISPLAY = {
    "ongoing":     "🟢 Ongoing (ဆက်လက်ထုတ်လုပ်နေဆဲ)",
    "translating": "🔵 Translating (ဘာသာပြန်နေဆဲ)",
    "complete":    "✅ Complete (ပြီးဆုံးပါပြီ)",
}


async def check_forcesub(client: Client, user_id: int) -> tuple[bool, list]:
    """
    User သည် ForceSub channels အားလုံးတွင် Join လုပ်ထားသလား စစ်ဆေးသည်。

    Returns:
        (all_joined: bool, missing_channels: list)
    """
    channels = await get_forcesub_channels()
    if not channels:
        return True, []

    missing = []
    for channel in channels:
        ch_id = channel.get("channel_id")
        try:
            member = await client.get_chat_member(ch_id, user_id)
            # Banned/Kicked → missing ထဲ ထည့်သည်
            status_str = str(member.status)
            if "banned" in status_str.lower() or "kicked" in status_str.lower():
                missing.append(channel)
        except UserNotParticipant:
            missing.append(channel)
        except Exception as e:
            logger.warning(f"Cannot check membership ch={ch_id} user={user_id}: {e}")

    return len(missing) == 0, missing


def parse_telegram_link(link: str) -> tuple[int, int] | None:
    """
    Private channel message link ကို parse လုပ်သည်。
    Format: https://t.me/c/{channel_id}/{message_id}

    Returns:
        (chat_id, message_id) tuple or None
    """
    if not link:
        return None
    link = link.strip()
    match = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if match:
        channel_id = int(f"-100{match.group(1)}")
        message_id = int(match.group(2))
        return channel_id, message_id
    return None


def is_telegram_private_link(link: str) -> bool:
    """Private channel link ဟုတ်မဟုတ် စစ်သည်"""
    if not link:
        return False
    return bool(re.match(r"https?://t\.me/c/\d+/\d+", link.strip()))


def format_series_footer(status: str, episodes: list) -> str:
    """Series status + episode count footer"""
    status_text = STATUS_DISPLAY.get(status, status)
    ep_count    = len(episodes)
    return f"\n\n📊 **Status:** {status_text}\n📋 **Episodes:** {ep_count} ကြိမ်"


def format_content_info(content: dict) -> str:
    """Content info text (Admin view)"""
    ctype  = "🎬 Movie" if content.get("type") == "movie" else "📺 Series"
    title  = content.get("title", "Untitled")
    review = content.get("review", "")
    chash  = content.get("content_hash", "N/A")

    text = f"{ctype} **{title}**\n"
    if review:
        text += f"\n📝 _{review[:300]}_\n"

    if content.get("type") == "series":
        episodes = content.get("episodes", [])
        status   = content.get("status", "ongoing")
        text += f"\n📋 Episodes: {len(episodes)} ကြိမ်"
        text += f"\n📊 Status: {STATUS_DISPLAY.get(status, status)}"
        if episodes:
            text += "\n\n**Episodes List:**"
            for i, ep in enumerate(episodes[:5], 1):
                text += f"\n  {i}. {ep.get('name', f'EP{i}')}"
            if len(episodes) > 5:
                text += f"\n  ... နှင့် {len(episodes) - 5} ကြိမ် ကျန်ရှိသည်"

    text += f"\n\n🔑 Hash: `{chash}`"
    return text


async def safe_delete_message(client: Client, chat_id: int, message_id: int) -> bool:
    """Message delete — error ဖြစ်လျှင် silently fail"""
    try:
        await client.delete_messages(chat_id, message_id)
        return True
    except Exception as e:
        logger.debug(f"Cannot delete msg {message_id} in {chat_id}: {e}")
        return False


async def safe_send_message(client: Client, chat_id: int, text: str, **kwargs) -> int | None:
    """Message send with FloodWait retry。Returns message_id or None。"""
    for attempt in range(3):
        try:
            msg = await client.send_message(chat_id, text, **kwargs)
            return msg.id
        except FloodWait as e:
            wait = e.value + 1
            logger.warning(f"FloodWait {wait}s (attempt {attempt + 1})")
            if attempt < 2:
                await asyncio.sleep(wait)
            else:
                raise
        except Exception as e:
            logger.error(f"send_message error: {e}")
            return None
    return None
