"""
dispatcher.py — TeleCMS FileStore Pro
Telegram update ကို parse လုပ်ပြီး admin/user handler ဆီ route ပေးသည်。
Pyrogram dispatcher မသုံးဘဲ raw dict routing လုပ်သည်。
"""
import logging
from typing import Any
from pyrogram import Client

from config import config
from admin import handle_admin_command, handle_admin_message, handle_admin_callback
from user import handle_start, handle_verify_callback, handle_chat_member_update

logger = logging.getLogger(__name__)


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in config.ADMIN_IDS


async def dispatch_update(client: Client, update: dict[str, Any]) -> None:
    """
    Webhook update တစ်ခုကို receive လုပ်ပြီး သင့်တော်တဲ့ handler ဆီ route ပေးသည်。
    """
    try:
        # ── chat_member / my_chat_member ──────────────────────────────────────
        if "chat_member" in update or "my_chat_member" in update:
            await handle_chat_member_update(client, update)
            return

        # ── callback_query ────────────────────────────────────────────────────
        if "callback_query" in update:
            cq      = update["callback_query"]
            user_id = cq.get("from", {}).get("id")
            data: str = cq.get("data", "")

            # User ForceSub verify callback — admin ဆိုရင်လည်း user handler ကို route
            if data.startswith("verify_"):
                await handle_verify_callback(client, cq)
                return

            # Admin callbacks — ALL other callbacks for admins
            if _is_admin(user_id):
                await handle_admin_callback(client, cq)
                return

            # Unknown callback from non-admin — answer to stop spinner
            try:
                await client.answer_callback_query(cq["id"])
            except Exception:
                pass
            return

        # ── message ───────────────────────────────────────────────────────────
        if "message" in update:
            msg       = update["message"]
            user_id   = msg.get("from", {}).get("id")
            chat_type = msg.get("chat", {}).get("type", "")
            text: str = msg.get("text", "") or ""

            # Group/Channel messages ကို ignore
            if chat_type in ("group", "supergroup", "channel"):
                return

            is_admin = _is_admin(user_id)

            # /start command
            if text.startswith("/start"):
                if is_admin:
                    # Admin /start → Admin main menu
                    await handle_admin_command(client, msg)
                else:
                    await handle_start(client, msg)
                return

            # /admin command (admins only)
            if is_admin and text.startswith("/admin"):
                await handle_admin_command(client, msg)
                return

            # Other commands — ignore for non-admins
            if text.startswith("/"):
                return

            # Admin state machine (text input during CMS flows)
            if is_admin:
                await handle_admin_message(client, msg)
                return

            # Regular users — non-/start messages ignored
            # (bot only supports deep link flow)

    except Exception as e:
        logger.exception(f"dispatch_update unhandled error: {e}")
