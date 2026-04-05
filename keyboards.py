"""
keyboards.py — TeleCMS FileStore Pro
Admin Panel နှင့် User UI အတွက် Inline Keyboard builders。
"""
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ════════════════════════════════════════════════════════════════
# Admin Keyboards
# ════════════════════════════════════════════════════════════════

def kb_admin_main() -> InlineKeyboardMarkup:
    """Admin Panel မူဆောင် Menu"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Content CMS",        callback_data="admin_cms"),
         InlineKeyboardButton("📢 Channel Post",       callback_data="admin_post")],
        [InlineKeyboardButton("🗄️ Storage Channels",   callback_data="admin_storage"),
         InlineKeyboardButton("🔒 ForceSub Channels",  callback_data="admin_forcesub")],
        [InlineKeyboardButton("📊 Statistics",         callback_data="admin_stats"),
         InlineKeyboardButton("⚙️ Maintenance",        callback_data="admin_maintenance")],
        [InlineKeyboardButton("🚪 Logout",             callback_data="admin_logout")],
    ])


def kb_admin_cms() -> InlineKeyboardMarkup:
    """Content Management System Menu"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Movie ထည့်မည်",       callback_data="cms_add_movie"),
         InlineKeyboardButton("📺 Series ထည့်မည်",      callback_data="cms_add_series")],
        [InlineKeyboardButton("📋 Content List ကြည့်မည်", callback_data="cms_list_0")],
        [InlineKeyboardButton("◀️ ပြန်သွားမည်",         callback_data="admin_main")],
    ])


def kb_admin_storage(channels: list) -> InlineKeyboardMarkup:
    """Storage Channels Management"""
    buttons = []
    for ch in channels:
        name  = ch.get("channel_name", "Unknown")
        ch_id = ch.get("channel_id")
        buttons.append([
            InlineKeyboardButton(f"🗑️ {name}", callback_data=f"del_storage_{ch_id}")
        ])
    buttons.append([
        InlineKeyboardButton("➕ Storage Channel ထည့်မည်", callback_data="add_storage_ch")
    ])
    buttons.append([InlineKeyboardButton("◀️ ပြန်သွားမည်", callback_data="admin_main")])
    return InlineKeyboardMarkup(buttons)


def kb_admin_forcesub(channels: list) -> InlineKeyboardMarkup:
    """ForceSub Channels Management"""
    buttons = []
    for ch in channels:
        name  = ch.get("channel_name", "Unknown")
        ch_id = ch.get("channel_id")
        buttons.append([
            InlineKeyboardButton(f"🗑️ {name}", callback_data=f"del_forcesub_{ch_id}")
        ])
    buttons.append([
        InlineKeyboardButton("➕ ForceSub Channel ထည့်မည်", callback_data="add_forcesub_ch")
    ])
    buttons.append([InlineKeyboardButton("◀️ ပြန်သွားမည်", callback_data="admin_main")])
    return InlineKeyboardMarkup(buttons)


def kb_content_list(contents: list, page: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    """Content List with Pagination"""
    buttons = []
    for c in contents:
        ctype = "🎬" if c.get("type") == "movie" else "📺"
        title = c.get("title", "Untitled")[:30]
        cid   = c.get("_id", "")
        buttons.append([
            InlineKeyboardButton(f"{ctype} {title}", callback_data=f"view_content_{cid}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ ရှေ့", callback_data=f"cms_list_{page - 1}"))
    if (page + 1) * 10 < total:
        nav.append(InlineKeyboardButton("နောက် ▶️", callback_data=f"cms_list_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("◀️ ပြန်သွားမည်", callback_data="admin_cms")])
    return InlineKeyboardMarkup(buttons)


def kb_content_actions(content_id: str) -> InlineKeyboardMarkup:
    """Individual content action buttons"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel တွင် Post တင်မည်",
                              callback_data=f"post_init_{content_id}")],
        [InlineKeyboardButton("✏️ Edit",   callback_data=f"edit_content_{content_id}"),
         InlineKeyboardButton("🗑️ Delete", callback_data=f"del_content_{content_id}")],
        [InlineKeyboardButton("◀️ List ကိုပြန်သွားမည်", callback_data="cms_list_0")],
    ])


def kb_series_status() -> InlineKeyboardMarkup:
    """Series status selection"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Ongoing",     callback_data="set_status_ongoing"),
         InlineKeyboardButton("🔵 Translating", callback_data="set_status_translating")],
        [InlineKeyboardButton("✅ Complete",    callback_data="set_status_complete")],
    ])


def kb_episode_actions() -> InlineKeyboardMarkup:
    """After adding an episode"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Episode ထပ်ထည့်မည်", callback_data="add_ep_more"),
         InlineKeyboardButton("✅ Episodes ပြီးပါပြီ",  callback_data="add_ep_done")],
        [InlineKeyboardButton("❌ ပယ်ဖျက်မည်",         callback_data="cancel")],
    ])


def kb_cancel() -> InlineKeyboardMarkup:
    """Simple cancel button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ ပယ်ဖျက်မည်", callback_data="cancel")]
    ])


def kb_skip_or_cancel(skip_data: str = "skip") -> InlineKeyboardMarkup:
    """Skip + Cancel buttons"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ ကျော်မည်",  callback_data=skip_data),
         InlineKeyboardButton("❌ ပယ်ဖျက်မည်", callback_data="cancel")],
    ])


def kb_confirm_delete(content_id: str) -> InlineKeyboardMarkup:
    """Delete confirmation"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ဟုတ်ကဲ့ ဖျက်မည်",
                              callback_data=f"confirm_del_{content_id}"),
         InlineKeyboardButton("❌ မဖျက်ပါ",
                              callback_data=f"view_content_{content_id}")],
    ])


def kb_edit_content(content_id: str, content_type: str) -> InlineKeyboardMarkup:
    """Edit content options"""
    buttons = [
        [InlineKeyboardButton("🖼️ Poster ပြောင်းမည်", callback_data=f"edit_poster_{content_id}"),
         InlineKeyboardButton("📝 Review ပြောင်းမည်", callback_data=f"edit_review_{content_id}")],
    ]
    if content_type == "series":
        buttons.append([
            InlineKeyboardButton("➕ Episode ထပ်ထည့်မည်",
                                 callback_data=f"edit_add_ep_{content_id}"),
            InlineKeyboardButton("📊 Status ပြောင်းမည်",
                                 callback_data=f"edit_status_{content_id}"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🔗 Video Link ပြောင်းမည်",
                                 callback_data=f"edit_link_{content_id}")
        ])
    buttons.append([
        InlineKeyboardButton("◀️ ပြန်သွားမည်", callback_data=f"view_content_{content_id}")
    ])
    return InlineKeyboardMarkup(buttons)


def kb_post_channel_confirm(channel_id: int, content_id: str) -> InlineKeyboardMarkup:
    """Confirm posting to a channel"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Post တင်မည်",
                              callback_data=f"confirm_post_{channel_id}_{content_id}"),
         InlineKeyboardButton("❌ မတင်ပါ",
                              callback_data=f"view_content_{content_id}")],
    ])


def kb_channel_select(channels: list, action: str = "post") -> InlineKeyboardMarkup:
    """Bot admin ဖြစ်တဲ့ channels list ကို buttons အဖြစ် ပြသည်"""
    buttons = []
    for ch in channels:
        ch_id   = ch["id"]
        name    = ch["title"][:35]
        buttons.append([
            InlineKeyboardButton(f"📢 {name}", callback_data=f"sel_ch_{action}_{ch_id}")
        ])
    buttons.append([InlineKeyboardButton("❌ ပယ်ဖျက်မည်", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


# ════════════════════════════════════════════════════════════════
# User Keyboards
# ════════════════════════════════════════════════════════════════

def kb_forcesub(missing_channels: list, content_hash: str) -> InlineKeyboardMarkup:
    """ForceSub — Join buttons + Verify button"""
    buttons = []
    for ch in missing_channels:
        username    = ch.get("channel_username")
        invite_link = ch.get("invite_link")
        name        = ch.get("channel_name", "Channel")

        if username:
            link = f"https://t.me/{username}"
        elif invite_link:
            link = invite_link
        else:
            continue

        buttons.append([
            InlineKeyboardButton(f"📢 {name} Join လုပ်ပါ ▶️", url=link)
        ])

    buttons.append([
        InlineKeyboardButton(
            "✅ Join လုပ်ပြီးပါပြီ — စစ်ဆေးပါ",
            callback_data=f"verify_{content_hash}",
        )
    ])
    return InlineKeyboardMarkup(buttons)


def kb_watch_now(content_hash: str, bot_username: str) -> InlineKeyboardMarkup:
    """Public channel post — Watch Now button"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "▶️ ကြည့်ရန်",
            url=f"https://t.me/{bot_username}?start={content_hash}",
        )
    ]])
