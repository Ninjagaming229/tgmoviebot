"""
user.py — TeleCMS FileStore Pro
/start deep link, ForceSub verify, content delivery,
auto-delete on channel leave features ကို handle လုပ်သည်。
"""
import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from database import (
    get_setting, get_content, get_forcesub_channels,
    save_user_messages, get_user_messages_by_channel, delete_user_messages_record,
)
from crypto import decode_content_id
from helpers import (
    check_forcesub, parse_telegram_link, is_telegram_private_link,
    format_series_footer,
)
from keyboards import kb_forcesub

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# /start Handler
# ════════════════════════════════════════════════════════════════

async def handle_start(client: Client, msg: dict) -> None:
    """
    /start command ကို handle လုပ်သည်。
    Deep link parameter ရှိလျှင် content delivery flow ကို စသည်。
    """
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "")

    # Maintenance mode check
    if await get_setting("maintenance_mode", False) and user_id not in config.ADMIN_IDS:
        await client.send_message(
            chat_id,
            "🔴 **Bot ကို ယာယီပိတ်ထားပါသည်**\n\n"
            "ကျေးဇူးပြု၍ နောက်မှ ပြန်ကြည့်ပါ。",
        )
        return

    parts = text.strip().split(maxsplit=1)
    if len(parts) > 1:
        # Deep link ရှိလျှင် — admin ဆိုရင်လည်း content ကြည့်နိုင်သည်
        content_hash = parts[1].strip()
        await _handle_deep_link(client, msg, user_id, chat_id, content_hash)
    else:
        # Deep link မရှိ — admin ဆိုရင် admin panel၊ user ဆိုရင် welcome
        if user_id in config.ADMIN_IDS:
            from admin import handle_admin_command
            await handle_admin_command(client, msg)
        else:
            await _send_welcome(client, chat_id)


async def _send_welcome(client: Client, chat_id: int) -> None:
    """Default welcome message"""
    await client.send_message(
        chat_id,
        "👋 **မင်္ဂလာပါ!**\n\n"
        "🎬 ဤ Bot သည် Movies & Series များကို\n"
        "   အလွယ်တကူ ကြည့်ရှုနိုင်ရန် ကူညီပေးသည်。\n\n"
        "📢 Channel မှ **ကြည့်ရန်** button ကို နှိပ်ပြီး\n"
        "   Content များကို ကြည့်ရှုနိုင်ပါသည်。\n\n"
        "━━━━━━━━━━━━━━━━━━━━",
    )


async def _handle_deep_link(
    client: Client, msg: dict, user_id: int, chat_id: int, content_hash: str
) -> None:
    """Deep link parameter decode → ForceSub check → deliver"""
    content_id = decode_content_id(content_hash)
    if not content_id:
        await client.send_message(
            chat_id,
            "❌ **Link မမှန်ပါ**\n\n"
            "Link သည် မသုံးနိုင်ပါ သို့မဟုတ် ပျက်စီးနေပါသည်。\n"
            "Channel မှ ထပ်မံ ကြည့်ပါ。",
        )
        return

    all_joined, missing = await check_forcesub(client, user_id)
    if not all_joined:
        await client.send_message(
            chat_id,
            "🔒 **Content ကြည့်ရှုရန် Channel Join လုပ်ရပါမည်**\n\n"
            "အောက်ပါ Channel(s) တွင် Join လုပ်ပြီး\n"
            "**✅ စစ်ဆေးပါ** button ကို နှိပ်ပါ:",
            reply_markup=kb_forcesub(missing, content_hash),
        )
        return

    content = await get_content(content_id)
    if not content:
        await client.send_message(
            chat_id,
            "❌ **Content မတွေ့ပါ**\n\nဤ content ကို ဖျက်ထားပြီ ဖြစ်နိုင်ပါသည်。",
        )
        return

    await _deliver_content(client, chat_id, user_id, content)


# ════════════════════════════════════════════════════════════════
# ForceSub Verify Callback
# ════════════════════════════════════════════════════════════════

async def handle_verify_callback(client: Client, cq: dict) -> None:
    """User ၏ ForceSub verify button ကို handle လုပ်သည်"""
    cq_id   = cq["id"]
    user_id = cq["from"]["id"]
    chat_id = cq["message"]["chat"]["id"]
    msg_id  = cq["message"]["message_id"]
    data    = cq.get("data", "")

    # callback_data format: "verify_{content_hash}"
    content_hash = data.removeprefix("verify_")
    content_id   = decode_content_id(content_hash)

    if not content_id:
        await client.answer_callback_query(cq_id, "❌ Link မမှန်ပါ!", show_alert=True)
        return

    all_joined, missing = await check_forcesub(client, user_id)
    if not all_joined:
        await client.answer_callback_query(
            cq_id,
            f"❌ {len(missing)} Channel တွင် Join မလုပ်ရသေးပါ!\n"
            "Channel Join လုပ်ပြီး ထပ်နှိပ်ပါ。",
            show_alert=True,
        )
        try:
            await client.edit_message_reply_markup(
                chat_id, msg_id, reply_markup=kb_forcesub(missing, content_hash)
            )
        except Exception:
            pass
        return

    await client.answer_callback_query(cq_id, "✅ Verified! Content ပေးပို့နေပါသည်...")

    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception:
        pass

    content = await get_content(content_id)
    if not content:
        await client.send_message(chat_id, "❌ Content မတွေ့ပါ!")
        return

    await _deliver_content(client, chat_id, user_id, content)


# ════════════════════════════════════════════════════════════════
# Content Delivery
# ════════════════════════════════════════════════════════════════

async def _deliver_content(
    client: Client, chat_id: int, user_id: int, content: dict
) -> None:
    """Content ကို user ထံ ပေးပို့သည်"""
    sent_ids: list[int] = []
    try:
        if content.get("type") == "movie":
            sent_ids = await _deliver_movie(client, chat_id, content)
        elif content.get("type") == "series":
            sent_ids = await _deliver_series(client, chat_id, content)

        # Auto-delete feature: message IDs ကို ForceSub channels ပေါ်မူတည်ပြီး save
        if sent_ids:
            forcesub_channels = await get_forcesub_channels()
            for ch in forcesub_channels:
                await save_user_messages(user_id, ch["channel_id"], sent_ids)

    except UserIsBlocked:
        logger.info(f"User {user_id} has blocked the bot")
    except InputUserDeactivated:
        logger.info(f"User {user_id} account is deactivated")
    except Exception as e:
        logger.error(f"Content delivery error user={user_id}: {e}")
        try:
            await client.send_message(
                chat_id,
                "❌ **Content ပေးပို့ရာတွင် Error ဖြစ်ပါသည်**\n\n"
                "ကျေးဇူးပြု၍ ထပ်မံကြိုးစားပါ。",
            )
        except Exception:
            pass


async def _deliver_movie(client: Client, chat_id: int, content: dict) -> list[int]:
    """Movie content ပေးပို့သည်"""
    sent_ids:  list[int] = []
    title      = content.get("title", "Movie")
    review     = content.get("review", "")
    video_link = content.get("video_link", "")

    caption = f"🎬 **{title}**"
    if review:
        caption += f"\n\n📝 {review}"

    if is_telegram_private_link(video_link):
        parsed = parse_telegram_link(video_link)
        if parsed:
            from_chat_id, from_msg_id = parsed
            try:
                sent = await client.copy_message(
                    chat_id=chat_id,
                    from_chat_id=from_chat_id,
                    message_id=from_msg_id,
                    caption=caption,
                )
                sent_ids.append(sent.id)
                return sent_ids
            except Exception as e:
                logger.warning(f"copy_message failed: {e}, falling back to button")

    # External link or fallback
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ ကြည့်ရန်", url=video_link)
    ]])
    sent = await client.send_message(chat_id, caption, reply_markup=keyboard)
    sent_ids.append(sent.id)
    return sent_ids


async def _deliver_series(client: Client, chat_id: int, content: dict) -> list[int]:
    """Series content ပေးပို့သည် (Header + Episodes)"""
    sent_ids: list[int] = []
    title    = content.get("title", "Series")
    review   = content.get("review", "")
    episodes = content.get("episodes", [])
    status   = content.get("status", "ongoing")

    # Header message
    header = f"📺 **{title}**"
    if review:
        header += f"\n\n📝 {review}"
    header += format_series_footer(status, episodes)

    header_msg = await client.send_message(chat_id, header)
    sent_ids.append(header_msg.id)

    # Episodes တစ်ခုချင်း ပေးပို့သည်
    for i, episode in enumerate(episodes, 1):
        ep_name = episode.get("name", f"Episode {i}")
        ep_link = episode.get("link", "")
        if not ep_link:
            continue

        if i > 1:
            await asyncio.sleep(0.5)  # FloodWait prevention

        if is_telegram_private_link(ep_link):
            parsed = parse_telegram_link(ep_link)
            if parsed:
                from_chat_id, from_msg_id = parsed
                try:
                    sent = await client.copy_message(
                        chat_id=chat_id,
                        from_chat_id=from_chat_id,
                        message_id=from_msg_id,
                        caption=f"📺 **{ep_name}** — {title}",
                    )
                    sent_ids.append(sent.id)
                    continue
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                except Exception as e:
                    logger.warning(f"copy_message failed for {ep_name}: {e}")

        # External link or fallback
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"▶️ {ep_name} ကြည့်ရန်", url=ep_link)
        ]])
        sent = await client.send_message(
            chat_id, f"📺 **{ep_name}**", reply_markup=keyboard
        )
        sent_ids.append(sent.id)

    return sent_ids


# ════════════════════════════════════════════════════════════════
# Auto-Delete on ForceSub Channel Leave
# ════════════════════════════════════════════════════════════════

async def handle_chat_member_update(client: Client, update: dict) -> None:
    """
    User သည် ForceSub channel မှ ထွက်သွားလျှင်
    သူ့ထံ ပေးပို့ထားသော messages များကို auto-delete လုပ်သည်。
    """
    member_data = update.get("chat_member") or update.get("my_chat_member", {})
    old_member  = member_data.get("old_chat_member", {})
    new_member  = member_data.get("new_chat_member", {})
    old_status  = old_member.get("status", "")
    new_status  = new_member.get("status", "")

    # Leave/kick event မဟုတ်ရင် ignore
    if new_status not in ("left", "kicked", "banned"):
        return
    if old_status not in ("member", "creator", "administrator", "restricted"):
        return

    left_user  = new_member.get("user", {})
    user_id    = left_user.get("id")
    channel_id = member_data.get("chat", {}).get("id")

    if not user_id or not channel_id:
        return

    # Bot ၏ own leave ကို ignore
    bot_me = await client.get_me()
    if user_id == bot_me.id:
        return

    logger.info(f"User {user_id} left/kicked from ch {channel_id} — deleting messages")

    msg_ids = await get_user_messages_by_channel(user_id, channel_id)
    if not msg_ids:
        return

    # Batch delete (max 100 per call)
    deleted_count = 0
    for i in range(0, len(msg_ids), 100):
        batch = msg_ids[i: i + 100]
        try:
            await client.delete_messages(user_id, batch)
            deleted_count += len(batch)
        except Exception as e:
            logger.warning(f"Cannot delete messages for user {user_id}: {e}")

    await delete_user_messages_record(user_id, channel_id)

    if deleted_count > 0:
        try:
            await client.send_message(
                user_id,
                "⚠️ **Channel မှ ထွက်သွားသောကြောင့်**\n\n"
                f"ပေးပို့ထားသော Content `{deleted_count}` ခုကို ဖျက်ပြီးပါပြီ。\n\n"
                "Channel တွင် ပြန် Join ဝင်ပြီး ထပ်မံကြည့်ရှုနိုင်ပါသည်。",
            )
        except Exception:
            pass

    logger.info(f"Deleted {deleted_count} messages for user {user_id} (left ch {channel_id})")
