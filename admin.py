"""
admin.py — TeleCMS FileStore Pro
Admin Panel handler — command, message, callback routing。
MongoDB state machine ဖြင့် multi-step conversations manage လုပ်သည်。
"""
import logging
from pyrogram import Client

from config import config
from database import (
    get_admin_state, set_admin_state, clear_admin_state,
    is_admin_logged_in, set_admin_session,
    add_storage_channel, remove_storage_channel, get_storage_channels,
    add_forcesub_channel, remove_forcesub_channel, get_forcesub_channels,
    create_content, get_content, update_content, delete_content,
    get_all_content, count_content, create_post,
    get_setting, set_setting,
    get_bot_channels,
)
from keyboards import (
    kb_admin_main, kb_admin_cms, kb_admin_storage, kb_admin_forcesub,
    kb_content_list, kb_content_actions, kb_series_status, kb_episode_actions,
    kb_cancel, kb_skip_or_cancel, kb_confirm_delete, kb_edit_content,
    kb_watch_now, kb_post_channel_confirm, kb_channel_select,
    kb_episode_list_delete,
)
from crypto import encode_content_id
from helpers import format_content_info, STATUS_DISPLAY

logger = logging.getLogger(__name__)

# ── Admin Conversation States ─────────────────────────────────────────────────
IDLE             = "IDLE"
AWAIT_PASSWORD   = "AWAIT_PASSWORD"
ADD_STORAGE_CH   = "ADD_STORAGE_CH"
ADD_FORCESUB_CH  = "ADD_FORCESUB_CH"
CMS_TITLE        = "CMS_TITLE"
CMS_POSTER       = "CMS_POSTER"
CMS_REVIEW       = "CMS_REVIEW"
CMS_VIDEO_LINK   = "CMS_VIDEO_LINK"
CMS_EP_NAME      = "CMS_EP_NAME"
CMS_EP_LINK      = "CMS_EP_LINK"
CMS_SERIES_STATUS= "CMS_SERIES_STATUS"
POST_SELECT_CH   = "POST_SELECT_CH"
EDIT_POSTER      = "EDIT_POSTER"
EDIT_REVIEW      = "EDIT_REVIEW"
EDIT_LINK        = "EDIT_LINK"
EDIT_EP_NAME     = "EDIT_EP_NAME"
EDIT_EP_LINK     = "EDIT_EP_LINK"


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ════════════════════════════════════════════════════════════════
# /admin (or /start for admins) Command Handler
# ════════════════════════════════════════════════════════════════

async def handle_admin_command(client: Client, msg: dict) -> None:
    """
    /admin command ကို handle လုပ်သည်。
    Login ဝင်ပြီးသားဆိုရင် Main Menu。 မဝင်ရသေးဆိုရင် password တောင်းသည်。
    """
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]

    if not is_admin(user_id):
        return

    if await is_admin_logged_in(user_id):
        await set_admin_state(user_id, IDLE)
        await client.send_message(
            chat_id,
            "🎛️ **TeleCMS Admin Panel**\n\nမင်္ဂလာပါ Admin! ဘာလုပ်ရမည်နည်း?",
            reply_markup=kb_admin_main(),
        )
    else:
        await set_admin_state(user_id, AWAIT_PASSWORD)
        await client.send_message(
            chat_id,
            "🔐 **Admin Login**\n\nPassword ထည့်ပါ:",
            reply_markup=kb_cancel(),
        )


# ════════════════════════════════════════════════════════════════
# Admin Text Message Handler (State Machine)
# ════════════════════════════════════════════════════════════════

async def handle_admin_message(client: Client, msg: dict) -> None:
    """Admin ၏ text messages ကို state machine ဖြင့် route လုပ်သည်"""
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()

    if not is_admin(user_id) or not text:
        return

    state_doc = await get_admin_state(user_id)
    state     = state_doc.get("state", IDLE)
    data      = state_doc.get("data", {})

    # Password check
    if state == AWAIT_PASSWORD:
        if text == config.ADMIN_PASSWORD:
            await set_admin_session(user_id, True)
            await clear_admin_state(user_id)
            await client.send_message(
                chat_id,
                "✅ **Login အောင်မြင်ပါသည်!**\n\nAdmin Panel မှ ကြိုဆိုပါသည်။",
                reply_markup=kb_admin_main(),
            )
        else:
            await client.send_message(chat_id, "❌ Password မှားနေပါသည်။ ထပ်မံကြိုးစားပါ:")
        return

    if not await is_admin_logged_in(user_id):
        await client.send_message(chat_id, "❌ /admin command ဖြင့် login ဝင်ပါ")
        return

    # CMS flow states
    if state == CMS_TITLE:
        data["title"] = text
        await set_admin_state(user_id, CMS_POSTER, data)
        await client.send_message(
            chat_id,
            "🖼️ **Poster Image URL ထည့်ပါ:**\n_(Direct image link ဖြစ်ရမည်)_",
            reply_markup=kb_cancel(),
        )

    elif state == CMS_POSTER:
        data["poster_url"] = text
        await set_admin_state(user_id, CMS_REVIEW, data)
        await client.send_message(
            chat_id,
            "📝 **Review/Description ထည့်ပါ:**\n_(ကျော်လိုလျှင် Skip button နှိပ်ပါ)_",
            reply_markup=kb_skip_or_cancel("skip_review"),
        )

    elif state == CMS_REVIEW:
        data["review"] = text
        await _proceed_after_review(client, chat_id, user_id, data)

    elif state == CMS_VIDEO_LINK:
        data["video_link"] = text
        await _save_movie(client, chat_id, user_id, data)

    elif state == CMS_EP_NAME:
        data["current_ep_name"] = text
        await set_admin_state(user_id, CMS_EP_LINK, data)
        await client.send_message(
            chat_id,
            f"🔗 **Episode '{text}' ၏ Link ထည့်ပါ:**\n"
            "_(Private: `https://t.me/c/xxx/yyy` သို့မဟုတ် External URL)_",
            reply_markup=kb_cancel(),
        )

    elif state == CMS_EP_LINK:
        ep_name = data.pop("current_ep_name", f"EP{len(data.get('episodes', [])) + 1}")
        if "episodes" not in data:
            data["episodes"] = []
        data["episodes"].append({"name": ep_name, "link": text})
        await set_admin_state(user_id, CMS_EP_NAME, data)
        await client.send_message(
            chat_id,
            f"✅ **Episode '{ep_name}' ထည့်ပြီးပါပြီ!**\n"
            f"📋 ယခု episodes: **{len(data['episodes'])}** ကြိမ်\n\n"
            "Episode ထပ်ထည့်မလား?",
            reply_markup=kb_episode_actions(),
        )

    elif state == POST_SELECT_CH:
        await _handle_post_channel_input(client, chat_id, user_id, text, data)

    elif state == EDIT_POSTER:
        cid = data.get("content_id")
        await update_content(cid, {"poster_url": text})
        await clear_admin_state(user_id)
        content = await get_content(cid)
        await client.send_message(
            chat_id,
            f"✅ Poster update ပြီးပါပြီ!\n\n{format_content_info(content)}",
            reply_markup=kb_content_actions(cid),
        )

    elif state == EDIT_REVIEW:
        cid = data.get("content_id")
        await update_content(cid, {"review": text})
        await clear_admin_state(user_id)
        content = await get_content(cid)
        await client.send_message(
            chat_id,
            f"✅ Review update ပြီးပါပြီ!\n\n{format_content_info(content)}",
            reply_markup=kb_content_actions(cid),
        )

    elif state == EDIT_LINK:
        cid = data.get("content_id")
        await update_content(cid, {"video_link": text})
        await clear_admin_state(user_id)
        content = await get_content(cid)
        await client.send_message(
            chat_id,
            f"✅ Video Link update ပြီးပါပြီ!\n\n{format_content_info(content)}",
            reply_markup=kb_content_actions(cid),
        )

    elif state == EDIT_EP_NAME:
        data["edit_ep_name"] = text
        await set_admin_state(user_id, EDIT_EP_LINK, data)
        await client.send_message(
            chat_id, f"🔗 Episode '{text}' ၏ Link ထည့်ပါ:", reply_markup=kb_cancel()
        )

    elif state == EDIT_EP_LINK:
        ep_name  = data.get("edit_ep_name", "Episode")
        cid      = data.get("content_id")
        content  = await get_content(cid)
        episodes = content.get("episodes", [])
        episodes.append({"name": ep_name, "link": text})
        await update_content(cid, {"episodes": episodes})
        data.pop("edit_ep_name", None)
        await set_admin_state(user_id, EDIT_EP_NAME, data)
        await client.send_message(
            chat_id,
            f"✅ Episode '{ep_name}' ထည့်ပြီးပါပြီ!\n"
            f"📋 ယခု episodes: {len(episodes)} ကြိမ်\n\nEpisode ထပ်ထည့်မလား?",
            reply_markup=kb_episode_actions(),
        )

    elif state == ADD_STORAGE_CH:
        await _add_storage_channel_by_input(client, chat_id, user_id, text)

    elif state == ADD_FORCESUB_CH:
        await _add_forcesub_channel_by_input(client, chat_id, user_id, text)


# ════════════════════════════════════════════════════════════════
# Admin Callback Query Handler
# ════════════════════════════════════════════════════════════════

async def handle_admin_callback(client: Client, cq: dict) -> None:
    """Admin callback queries (button presses) ကို handle လုပ်သည်"""
    cq_id   = cq["id"]
    user_id = cq["from"]["id"]
    chat_id = cq["message"]["chat"]["id"]
    msg_id  = cq["message"]["message_id"]
    data    = cq.get("data", "")

    if not is_admin(user_id):
        await _ack(client, cq_id, "❌ Admin access မရှိပါ!", alert=True)
        return

    # Cancel
    if data == "cancel":
        await _ack(client, cq_id, "ပယ်ဖျက်ပြီးပါပြီ")
        await clear_admin_state(user_id)
        if await is_admin_logged_in(user_id):
            await client.edit_message_text(
                chat_id, msg_id, "🎛️ **Admin Panel**", reply_markup=kb_admin_main()
            )
        else:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception:
                pass
        return

    if not await is_admin_logged_in(user_id):
        await _ack(client, cq_id, "❌ /admin ဖြင့် login ဝင်ပါ", alert=True)
        return

    await _ack(client, cq_id)

    # ── Navigation ────────────────────────────────────────────────────────────
    if data == "admin_main":
        await set_admin_state(user_id, IDLE)
        await client.edit_message_text(
            chat_id, msg_id,
            "🎛️ **TeleCMS Admin Panel**\n\nဘာလုပ်ရမည်နည်း?",
            reply_markup=kb_admin_main(),
        )

    elif data == "admin_logout":
        await set_admin_session(user_id, False)
        await clear_admin_state(user_id)
        await client.edit_message_text(
            chat_id, msg_id,
            "✅ Logout လုပ်ပြီးပါပြီ!\n\n/admin ဖြင့် ပြန် login ဝင်နိုင်ပါသည်。",
        )

    # ── Maintenance ───────────────────────────────────────────────────────────
    elif data == "admin_maintenance":
        current = await get_setting("maintenance_mode", False)
        new_val = not current
        await set_setting("maintenance_mode", new_val)
        status  = "🔴 Maintenance Mode **ON**" if new_val else "🟢 Maintenance Mode **OFF**"
        await client.edit_message_text(
            chat_id, msg_id,
            f"{status}\n\nBot ကို "
            f"{'ယာယီပိတ်ထားပါပြီ ⛔' if new_val else 'ပြန်ဖွင့်ထားပါပြီ ✅'}",
            reply_markup=kb_admin_main(),
        )

    # ── Statistics ────────────────────────────────────────────────────────────
    elif data == "admin_stats":
        movies    = await count_content("movie")
        series    = await count_content("series")
        channels_s = len(await get_storage_channels())
        channels_f = len(await get_forcesub_channels())
        await client.edit_message_text(
            chat_id, msg_id,
            f"📊 **Statistics**\n\n"
            f"🎬 Movies: **{movies}**\n"
            f"📺 Series: **{series}**\n"
            f"🗄️ Storage Channels: **{channels_s}**\n"
            f"🔒 ForceSub Channels: **{channels_f}**",
            reply_markup=kb_admin_main(),
        )

    # ── Storage Channels ──────────────────────────────────────────────────────
    elif data == "admin_storage":
        channels = await get_storage_channels()
        await client.edit_message_text(
            chat_id, msg_id,
            "🗄️ **Storage Channels**\n\n"
            "File store မည့် private channels.\n"
            "Channel ကို နှိပ်လျှင် ဖျက်နိုင်သည်:\n\n"
            "_(Bot ကို Channel Admin ထားရပါမည်)_",
            reply_markup=kb_admin_storage(channels),
        )

    elif data == "add_storage_ch":
        channels = await _get_bot_channels(client)
        if channels:
            await client.edit_message_text(
                chat_id, msg_id,
                "🗄️ **Storage Channel အဖြစ် ထည့်မည့် Channel ရွေးပါ:**",
                reply_markup=kb_channel_select(channels, "storage"),
            )
        else:
            await set_admin_state(user_id, ADD_STORAGE_CH)
            await client.edit_message_text(
                chat_id, msg_id,
                "🗄️ **Storage Channel ထည့်မည်**\n\n"
                "Channel ID (`-100xxxxxxx`) သို့မဟုတ် `@username` ထည့်ပါ:\n\n"
                "_(Bot ကို Channel Admin ထားပြီး ဖြစ်ရမည်)_",
                reply_markup=kb_cancel(),
            )

    elif data.startswith("del_storage_"):
        ch_id = int(data.removeprefix("del_storage_"))
        await remove_storage_channel(ch_id)
        channels = await get_storage_channels()
        await client.edit_message_text(
            chat_id, msg_id, "🗄️ **Storage Channels** _(ဖျက်ပြီးပါပြီ)_",
            reply_markup=kb_admin_storage(channels),
        )

    # ── ForceSub Channels ─────────────────────────────────────────────────────
    elif data == "admin_forcesub":
        channels = await get_forcesub_channels()
        await client.edit_message_text(
            chat_id, msg_id,
            "🔒 **ForceSub Channels**\n\n"
            "Users ဤ channels တွင် Join မလုပ်မချင်း content မကြည့်ရ.\n"
            "Channel ကို နှိပ်လျှင် ဖျက်နိုင်သည်:",
            reply_markup=kb_admin_forcesub(channels),
        )

    elif data == "add_forcesub_ch":
        channels = await _get_bot_channels(client)
        if channels:
            await client.edit_message_text(
                chat_id, msg_id,
                "🔒 **ForceSub Channel အဖြစ် ထည့်မည့် Channel ရွေးပါ:**",
                reply_markup=kb_channel_select(channels, "forcesub"),
            )
        else:
            await set_admin_state(user_id, ADD_FORCESUB_CH)
            await client.edit_message_text(
                chat_id, msg_id,
                "🔒 **ForceSub Channel ထည့်မည်**\n\n"
                "Channel ID (`-100xxxxxxx`) သို့မဟုတ် `@username` ထည့်ပါ:\n\n"
                "_(Public channel ဖြစ်ရမည်)_",
                reply_markup=kb_cancel(),
            )

    elif data.startswith("del_forcesub_"):
        ch_id = int(data.removeprefix("del_forcesub_"))
        await remove_forcesub_channel(ch_id)
        channels = await get_forcesub_channels()
        await client.edit_message_text(
            chat_id, msg_id, "🔒 **ForceSub Channels** _(ဖျက်ပြီးပါပြီ)_",
            reply_markup=kb_admin_forcesub(channels),
        )

    # ── Content CMS ───────────────────────────────────────────────────────────
    elif data == "admin_cms":
        await client.edit_message_text(
            chat_id, msg_id,
            "📺 **Content Management System**\n\nဘာလုပ်ရမည်နည်း?",
            reply_markup=kb_admin_cms(),
        )

    elif data in ("cms_add_movie", "cms_add_series"):
        ctype     = "movie" if data == "cms_add_movie" else "series"
        type_text = "🎬 Movie" if ctype == "movie" else "📺 Series"
        await set_admin_state(user_id, CMS_TITLE, {"type": ctype})
        await client.edit_message_text(
            chat_id, msg_id,
            f"{type_text} **ထည့်မည်**\n\n📝 Title ထည့်ပါ:",
            reply_markup=kb_cancel(),
        )

    elif data.startswith("cms_list_"):
        page  = int(data.removeprefix("cms_list_"))
        total = await count_content()
        contents = await get_all_content(limit=10, skip=page * 10)
        if not contents:
            await client.edit_message_text(
                chat_id, msg_id,
                "📋 **Content List**\n\n_Content မရှိသေးပါ_\n\nCMS မှ ထည့်ပါ:",
                reply_markup=kb_admin_cms(),
            )
            return
        await client.edit_message_text(
            chat_id, msg_id,
            f"📋 **Content List** ({total} ခု)\n\nContent ရွေးပါ:",
            reply_markup=kb_content_list(contents, page, total),
        )

    elif data.startswith("view_content_"):
        content_id = data.removeprefix("view_content_")
        content    = await get_content(content_id)
        if not content:
            await client.edit_message_text(
                chat_id, msg_id, "❌ Content မတွေ့ပါ!", reply_markup=kb_admin_cms()
            )
            return

        # POST_SELECT_CH state မှာ ဆိုရင် post confirm ပြ
        state_doc  = await get_admin_state(user_id)
        state_data = state_doc.get("data", {})
        if state_doc.get("state") == POST_SELECT_CH and state_data.get("channel_id"):
            channel_id   = state_data["channel_id"]
            channel_name = state_data.get("channel_name", str(channel_id))
            await set_admin_state(user_id, IDLE, {})
            await client.edit_message_text(
                chat_id, msg_id,
                f"📢 **Post Confirm**\n\n"
                f"Channel: **{channel_name}** (`{channel_id}`)\n"
                f"Content: **{content.get('title')}**\n\nPost တင်မည်လား?",
                reply_markup=kb_post_channel_confirm(channel_id, content_id),
            )
            return

        # Normal CMS view
        await client.edit_message_text(
            chat_id, msg_id,
            format_content_info(content),
            reply_markup=kb_content_actions(content_id),
        )

    elif data.startswith("del_content_"):
        content_id = data.removeprefix("del_content_")
        content    = await get_content(content_id)
        title      = content.get("title", "?") if content else "?"
        await client.edit_message_text(
            chat_id, msg_id,
            f"🗑️ **'{title}' ကို ဖျက်မည်?**\n\nဤ action ကို ပြန်မလုပ်နိုင်ပါ!",
            reply_markup=kb_confirm_delete(content_id),
        )

    elif data.startswith("confirm_del_"):
        content_id = data.removeprefix("confirm_del_")
        await delete_content(content_id)
        total    = await count_content()
        contents = await get_all_content(limit=10)
        await client.edit_message_text(
            chat_id, msg_id,
            f"✅ **Content ဖျက်ပြီးပါပြီ!**\n\nကျန် Content: {total} ခု",
            reply_markup=kb_content_list(contents, 0, total),
        )

    # ── Edit Content ──────────────────────────────────────────────────────────
    elif data.startswith("edit_content_"):
        content_id = data.removeprefix("edit_content_")
        content    = await get_content(content_id)
        if not content:
            await _ack(client, cq_id, "❌ Content မတွေ့ပါ!", alert=True)
            return
        await client.edit_message_text(
            chat_id, msg_id,
            f"✏️ **Edit: {content.get('title')}**\n\nဘာ edit မည်နည်း?",
            reply_markup=kb_edit_content(content_id, content.get("type", "movie")),
        )

    elif data.startswith("edit_poster_"):
        content_id = data.removeprefix("edit_poster_")
        await set_admin_state(user_id, EDIT_POSTER, {"content_id": content_id})
        await client.edit_message_text(
            chat_id, msg_id, "🖼️ **Poster အသစ် URL ထည့်ပါ:**", reply_markup=kb_cancel()
        )

    elif data.startswith("edit_review_"):
        content_id = data.removeprefix("edit_review_")
        await set_admin_state(user_id, EDIT_REVIEW, {"content_id": content_id})
        await client.edit_message_text(
            chat_id, msg_id, "📝 **Review အသစ် ထည့်ပါ:**", reply_markup=kb_cancel()
        )

    elif data.startswith("edit_link_"):
        content_id = data.removeprefix("edit_link_")
        await set_admin_state(user_id, EDIT_LINK, {"content_id": content_id})
        await client.edit_message_text(
            chat_id, msg_id, "🔗 **Video Link အသစ် ထည့်ပါ:**", reply_markup=kb_cancel()
        )

    elif data.startswith("edit_status_"):
        content_id = data.removeprefix("edit_status_")
        await set_admin_state(user_id, CMS_SERIES_STATUS, {"content_id": content_id, "edit_mode": True})
        await client.edit_message_text(
            chat_id, msg_id, "📊 **Status အသစ် ရွေးပါ:**", reply_markup=kb_series_status()
        )

    elif data.startswith("edit_add_ep_"):
        content_id = data.removeprefix("edit_add_ep_")
        await set_admin_state(user_id, EDIT_EP_NAME, {"content_id": content_id})
        await client.edit_message_text(
            chat_id, msg_id, "📝 **Episode Name ထည့်ပါ:**", reply_markup=kb_cancel()
        )

    # ── Series Status Selection ───────────────────────────────────────────────
    elif data.startswith("set_status_"):
        status     = data.removeprefix("set_status_")
        state_doc  = await get_admin_state(user_id)
        state_data = state_doc.get("data", {})

        if state_data.get("edit_mode"):
            content_id = state_data.get("content_id")
            await update_content(content_id, {"status": status})
            await clear_admin_state(user_id)
            content = await get_content(content_id)
            await client.edit_message_text(
                chat_id, msg_id,
                f"✅ Status update ပြီးပါပြီ!\n\n{format_content_info(content)}",
                reply_markup=kb_content_actions(content_id),
            )
        else:
            await _save_series(client, chat_id, msg_id, user_id, state_data, status)

    # ── Episode Actions ───────────────────────────────────────────────────────
    elif data == "add_ep_more":
        state_doc  = await get_admin_state(user_id)
        state_data = state_doc.get("data", {})
        ep_count   = len(state_data.get("episodes", []))
        await set_admin_state(user_id, CMS_EP_NAME, state_data)
        await client.edit_message_text(
            chat_id, msg_id,
            f"📝 **Episode {ep_count + 1} ၏ Name ထည့်ပါ:**",
            reply_markup=kb_cancel(),
        )

    elif data == "add_ep_done":
        state_doc  = await get_admin_state(user_id)
        state_data = state_doc.get("data", {})
        ep_count   = len(state_data.get("episodes", []))
        await set_admin_state(user_id, CMS_SERIES_STATUS, state_data)
        await client.edit_message_text(
            chat_id, msg_id,
            f"📊 **Series Status ရွေးပါ:**\n📋 Episodes: {ep_count} ကြိမ်",
            reply_markup=kb_series_status(),
        )

    elif data == "skip_review":
        state_doc  = await get_admin_state(user_id)
        state_data = state_doc.get("data", {})
        state_data["review"] = ""
        await _proceed_after_review(client, chat_id, user_id, state_data, msg_id=msg_id)

    # ── Public Channel Posting ────────────────────────────────────────────────
    elif data == "admin_post":
        channels = await _get_bot_channels(client)
        await set_admin_state(user_id, POST_SELECT_CH, {})
        if channels:
            await client.edit_message_text(
                chat_id, msg_id,
                "📢 **Post တင်မည့် Channel ရွေးပါ:**",
                reply_markup=kb_channel_select(channels, "post"),
            )
        else:
            await client.edit_message_text(
                chat_id, msg_id,
                "📢 **Channel Post**\n\n"
                "Channel ID (`-100xxxxxxxx`) သို့မဟုတ် `@username` ထည့်ပါ:",
                reply_markup=kb_cancel(),
            )

    elif data.startswith("post_init_"):
        content_id = data.removeprefix("post_init_")
        channels = await _get_bot_channels(client)
        await set_admin_state(user_id, POST_SELECT_CH, {"content_id": content_id})
        if channels:
            await client.edit_message_text(
                chat_id, msg_id,
                "📢 **Post တင်မည့် Channel ရွေးပါ:**",
                reply_markup=kb_channel_select(channels, f"post_c_{content_id}"),
            )
        else:
            await client.edit_message_text(
                chat_id, msg_id,
                "📢 **Post တင်မည်**\n\n"
                "Channel ID ထည့်ပါ:\n_(Format: `-100xxxxxxxx` သို့မဟုတ် `@username`)_",
                reply_markup=kb_cancel(),
            )

    elif data.startswith("del_ep_list_"):
        content_id = data.removeprefix("del_ep_list_")
        content    = await get_content(content_id)
        if not content:
            await _ack(client, cq_id, "❌ Content မတွေ့ပါ!", alert=True)
            return
        episodes = content.get("episodes", [])
        if not episodes:
            await _ack(client, cq_id, "Episode မရှိသေးပါ", alert=True)
            return
        await client.edit_message_text(
            chat_id, msg_id,
            f"🗑️ **ဖျက်မည့် Episode ရွေးပါ:**\n_(Content: {content.get('title')})_",
            reply_markup=kb_episode_list_delete(episodes, content_id),
        )

    elif data.startswith("del_ep_"):
        # Format: del_ep_{content_id}_{index}
        rest       = data.removeprefix("del_ep_")
        sep        = rest.rindex("_")
        content_id = rest[:sep]
        ep_index   = int(rest[sep + 1:])
        content    = await get_content(content_id)
        if not content:
            await _ack(client, cq_id, "❌ Content မတွေ့ပါ!", alert=True)
            return
        episodes = content.get("episodes", [])
        if ep_index >= len(episodes):
            await _ack(client, cq_id, "❌ Episode မတွေ့ပါ!", alert=True)
            return
        removed = episodes.pop(ep_index)
        await update_content(content_id, {"episodes": episodes})
        content = await get_content(content_id)
        await client.edit_message_text(
            chat_id, msg_id,
            f"✅ **'{removed.get('name', 'Episode')}' ဖျက်ပြီးပါပြီ!**\n\n"
            f"{format_content_info(content)}",
            reply_markup=kb_content_actions(content_id),
        )

    elif data.startswith("sel_ch_"):
        # Format: sel_ch_{action}_{channel_id}
        # action: post, storage, forcesub, post_c_{content_id}
        rest = data.removeprefix("sel_ch_")
        # Last token is channel_id, everything before is action
        parts = rest.rsplit("_", 1)
        action     = parts[0]  # e.g. "post", "storage", "forcesub", "post_c_<id>"
        channel_id = int(parts[1])

        try:
            channel_chat = await client.get_chat(channel_id)
        except Exception as e:
            await _ack(client, cq_id, f"❌ Channel info ရလာမရ: {e}", alert=True)
            return

        if action == "storage":
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(channel_id)
            except Exception:
                pass
            await add_storage_channel(channel_id, channel_chat.title, invite_link)
            await client.edit_message_text(
                chat_id, msg_id,
                f"✅ **Storage Channel ထည့်ပြီးပါပြီ!**\n"
                f"📢 {channel_chat.title} (`{channel_id}`)",
                reply_markup=kb_admin_main(),
            )

        elif action == "forcesub":
            username    = getattr(channel_chat, "username", None)
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(channel_id)
            except Exception:
                pass
            await add_forcesub_channel(channel_id, channel_chat.title, username, invite_link)
            await client.edit_message_text(
                chat_id, msg_id,
                f"✅ **ForceSub Channel ထည့်ပြီးပါပြီ!**\n"
                f"📢 {channel_chat.title} (`{channel_id}`)",
                reply_markup=kb_admin_main(),
            )

        elif action == "post":
            # Channel ရွေးပြီး — content ရွေးရန် list ပြ
            state_doc  = await get_admin_state(user_id)
            state_data = state_doc.get("data", {})
            state_data["channel_id"]   = channel_id
            state_data["channel_name"] = channel_chat.title
            await set_admin_state(user_id, POST_SELECT_CH, state_data)
            total    = await count_content()
            contents = await get_all_content(limit=10)
            if not contents:
                await client.edit_message_text(
                    chat_id, msg_id,
                    "❌ Content မရှိသေးပါ! CMS မှ ထည့်ပါ:",
                    reply_markup=kb_admin_cms(),
                )
                return
            await client.edit_message_text(
                chat_id, msg_id,
                f"📋 **Content ရွေးပါ**\n_(Channel: {channel_chat.title})_",
                reply_markup=kb_content_list(contents, 0, total),
            )

        elif action.startswith("post_c_"):
            # Content ရွေးပြီး channel ရွေးတာ — confirm ပြ
            content_id = action.removeprefix("post_c_")
            content    = await get_content(content_id)
            if not content:
                await _ack(client, cq_id, "❌ Content မတွေ့ပါ!", alert=True)
                return
            await set_admin_state(user_id, IDLE, {})
            await client.edit_message_text(
                chat_id, msg_id,
                f"📢 **Post Confirm**\n\n"
                f"Channel: **{channel_chat.title}** (`{channel_id}`)\n"
                f"Content: **{content.get('title')}**\n\nPost တင်မည်လား?",
                reply_markup=kb_post_channel_confirm(channel_id, content_id),
            )

    elif data.startswith("confirm_post_"):
        # Format: confirm_post_{channel_id}_{content_id}
        rest       = data.removeprefix("confirm_post_")
        sep_idx    = rest.index("_")
        channel_id = int(rest[:sep_idx])
        content_id = rest[sep_idx + 1:]
        await _execute_post(client, chat_id, msg_id, user_id, channel_id, content_id)


# ════════════════════════════════════════════════════════════════
# Private Helpers
# ════════════════════════════════════════════════════════════════

async def _ack(client: Client, cq_id: str, text: str = "", alert: bool = False) -> None:
    """Callback query answer"""
    try:
        await client.answer_callback_query(cq_id, text=text, show_alert=alert)
    except Exception:
        pass


async def _proceed_after_review(
    client: Client, chat_id: int, user_id: int, data: dict,
    msg_id: int | None = None,
) -> None:
    """Review step ပြီးနောက် content type ပေါ်မူတည်၍ route လုပ်သည်"""
    ctype = data.get("type")
    if ctype == "movie":
        await set_admin_state(user_id, CMS_VIDEO_LINK, data)
        text = (
            "🔗 **Video Link ထည့်ပါ:**\n\n"
            "**Private Channel Link:**\n`https://t.me/c/{channel_id}/{msg_id}`\n\n"
            "**External URL:**\n`https://drive.google.com/...` etc."
        )
        if msg_id:
            await client.edit_message_text(chat_id, msg_id, text, reply_markup=kb_cancel())
        else:
            await client.send_message(chat_id, text, reply_markup=kb_cancel())
    elif ctype == "series":
        await set_admin_state(user_id, CMS_EP_NAME, data)
        text = "📝 **Episode 1 ၏ Name ထည့်ပါ:**\n_(ဥပမာ: EP01, Episode 1)_"
        if msg_id:
            await client.edit_message_text(chat_id, msg_id, text, reply_markup=kb_cancel())
        else:
            await client.send_message(chat_id, text, reply_markup=kb_cancel())


async def _save_movie(client: Client, chat_id: int, user_id: int, data: dict) -> None:
    """Movie content DB ထဲ သိမ်းပြီး success message ပြသည်"""
    content_doc = {
        "type":       "movie",
        "title":      data.get("title", "Untitled"),
        "poster_url": data.get("poster_url", ""),
        "review":     data.get("review", ""),
        "video_link": data.get("video_link", ""),
    }
    content_id   = await create_content(content_doc)
    content_hash = encode_content_id(content_id)
    await update_content(content_id, {"content_hash": content_hash})

    me        = await client.get_me()
    deep_link = f"https://t.me/{me.username}?start={content_hash}"
    await clear_admin_state(user_id)
    await client.send_message(
        chat_id,
        f"✅ **Movie ထည့်ပြီးပါပြီ!**\n\n"
        f"🎬 Title: **{data.get('title')}**\n"
        f"🔗 Deep Link:\n`{deep_link}`",
        reply_markup=kb_admin_main(),
    )


async def _save_series(
    client: Client, chat_id: int, msg_id: int, user_id: int,
    data: dict, status: str,
) -> None:
    """Series content DB ထဲ သိမ်းပြီး success message ပြသည်"""
    content_doc = {
        "type":       "series",
        "title":      data.get("title", "Untitled"),
        "poster_url": data.get("poster_url", ""),
        "review":     data.get("review", ""),
        "episodes":   data.get("episodes", []),
        "status":     status,
    }
    content_id   = await create_content(content_doc)
    content_hash = encode_content_id(content_id)
    await update_content(content_id, {"content_hash": content_hash})

    me        = await client.get_me()
    deep_link = f"https://t.me/{me.username}?start={content_hash}"
    await clear_admin_state(user_id)
    await client.edit_message_text(
        chat_id, msg_id,
        f"✅ **Series ထည့်ပြီးပါပြီ!**\n\n"
        f"📺 Title: **{data.get('title')}**\n"
        f"📋 Episodes: {len(data.get('episodes', []))} ကြိမ်\n"
        f"📊 Status: {STATUS_DISPLAY.get(status, status)}\n\n"
        f"🔗 Deep Link:\n`{deep_link}`",
        reply_markup=kb_admin_main(),
    )


async def _add_storage_channel_by_input(
    client: Client, chat_id: int, user_id: int, text: str
) -> None:
    """Storage channel ကို text input မှ ထည့်သည်"""
    try:
        identifier = text if text.startswith("@") else int(text) if text.lstrip("-").isdigit() else None
        if identifier is None:
            await client.send_message(
                chat_id, "❌ Channel ID (`-100xxx`) သို့မဟုတ် `@username` ထည့်ပါ:"
            )
            return
        chat = await client.get_chat(identifier)
        invite_link = None
        try:
            invite_link = await client.export_chat_invite_link(chat.id)
        except Exception:
            pass
        await add_storage_channel(chat.id, chat.title, invite_link)
        await clear_admin_state(user_id)
        await client.send_message(
            chat_id,
            f"✅ **Storage Channel ထည့်ပြီးပါပြီ!**\n"
            f"📢 Name: **{chat.title}**\n🆔 ID: `{chat.id}`",
            reply_markup=kb_admin_main(),
        )
    except Exception as e:
        await client.send_message(chat_id, f"❌ Error: `{e}`\nထပ်မံကြိုးစားပါ:")


async def _add_forcesub_channel_by_input(
    client: Client, chat_id: int, user_id: int, text: str
) -> None:
    """ForceSub channel ကို text input မှ ထည့်သည်"""
    try:
        identifier = text if text.startswith("@") else int(text) if text.lstrip("-").isdigit() else None
        if identifier is None:
            await client.send_message(
                chat_id, "❌ Channel ID (`-100xxx`) သို့မဟုတ် `@username` ထည့်ပါ:"
            )
            return
        chat     = await client.get_chat(identifier)
        username = getattr(chat, "username", None)
        invite_link = None
        try:
            invite_link = await client.export_chat_invite_link(chat.id)
        except Exception:
            pass
        await add_forcesub_channel(chat.id, chat.title, username, invite_link)
        await clear_admin_state(user_id)
        await client.send_message(
            chat_id,
            f"✅ **ForceSub Channel ထည့်ပြီးပါပြီ!**\n"
            f"📢 Name: **{chat.title}**\n"
            f"🆔 ID: `{chat.id}`\n"
            f"👤 Username: @{username or 'N/A'}",
            reply_markup=kb_admin_main(),
        )
    except Exception as e:
        await client.send_message(chat_id, f"❌ Error: `{e}`\nထပ်မံကြိုးစားပါ:")


async def _get_bot_channels(client) -> list[dict]:
    """
    Bot က admin ဖြစ်တဲ့ channels တွေကို DB မှ ဖတ်သည်။
    my_chat_member event မှတဆင့် bot promoted/demoted ဖြစ်တိုင်း auto-update ဖြစ်သည်။
    get_dialogs() မသုံးတော့ (bots မှာ အလုပ်မလုပ်ဘူး)။
    """
    return await get_bot_channels()


async def _handle_post_channel_input(
    client: Client, chat_id: int, user_id: int, text: str, state_data: dict
) -> None:
    """Post channel input ကို process လုပ်သည်"""
    try:
        identifier = text if text.startswith("@") else int(text) if text.lstrip("-").isdigit() else None
        if identifier is None:
            await client.send_message(
                chat_id, "❌ Channel ID (`-100xxx`) သို့မဟုတ် `@username` ထည့်ပါ:"
            )
            return
        channel_chat = await client.get_chat(identifier)
        channel_id   = channel_chat.id
        content_id   = state_data.get("content_id")

        if content_id:
            content = await get_content(content_id)
            if not content:
                await client.send_message(chat_id, "❌ Content မတွေ့ပါ!")
                return
            await set_admin_state(user_id, IDLE, {})
            await client.send_message(
                chat_id,
                f"📢 **Post Confirm**\n\n"
                f"Channel: **{channel_chat.title}** (`{channel_id}`)\n"
                f"Content: **{content.get('title')}**\n\nPost တင်မည်လား?",
                reply_markup=kb_post_channel_confirm(channel_id, content_id),
            )
        else:
            state_data["channel_id"]   = channel_id
            state_data["channel_name"] = channel_chat.title
            await set_admin_state(user_id, POST_SELECT_CH, state_data)
            total    = await count_content()
            contents = await get_all_content(limit=10)
            if not contents:
                await client.send_message(
                    chat_id, "❌ Content မရှိသေးပါ! CMS မှ ထည့်ပါ:",
                    reply_markup=kb_admin_cms(),
                )
                return
            await client.send_message(
                chat_id,
                f"📋 **Content ရွေးပါ** (Channel: {channel_chat.title}):",
                reply_markup=kb_content_list(contents, 0, total),
            )
    except Exception as e:
        await client.send_message(chat_id, f"❌ Error: `{e}`")


async def _execute_post(
    client: Client, chat_id: int, msg_id: int, user_id: int,
    channel_id: int, content_id: str,
) -> None:
    """Content ကို Public channel တွင် post တင်သည်"""
    content = await get_content(content_id)
    if not content:
        await client.edit_message_text(
            chat_id, msg_id, "❌ Content မတွေ့ပါ!", reply_markup=kb_admin_main()
        )
        return

    me           = await client.get_me()
    content_hash = content.get("content_hash", "")
    title        = content.get("title", "Untitled")
    review       = content.get("review", "")
    ctype        = "🎬 Movie" if content.get("type") == "movie" else "📺 Series"

    caption = f"{ctype} **{title}**"
    if review:
        caption += f"\n\n📝 {review}"

    watch_btn = kb_watch_now(content_hash, me.username)

    try:
        sent = await client.send_photo(
            channel_id,
            photo=content.get("poster_url", ""),
            caption=caption,
            reply_markup=watch_btn,
        )
        await create_post(content_id, channel_id, sent.id)
        await clear_admin_state(user_id)
        await client.edit_message_text(
            chat_id, msg_id,
            f"✅ **Post တင်ပြီးပါပြီ!**\n\n"
            f"📢 Channel ID: `{channel_id}`\n"
            f"🎬 Content: **{title}**\n"
            f"🆔 Message ID: `{sent.id}`",
            reply_markup=kb_admin_main(),
        )
    except Exception as e:
        await client.edit_message_text(
            chat_id, msg_id,
            f"❌ **Post တင်မရပါ!**\n\nError: `{e}`\n\n"
            "Bot ကို Channel Admin ထားထားမှ post တင်နိုင်ပါသည်。",
            reply_markup=kb_admin_main(),
        )
