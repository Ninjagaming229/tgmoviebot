"""
config.py — TeleCMS FileStore Pro
Environment variables loader. Vercel Secrets မှ တိုက်ရိုက် os.environ ဖတ်သည်။
python-dotenv မသုံးဘဲ Vercel Environment Variables ကို အသုံးပြုသည်။
"""
import os


class Config:
    """Bot configuration — Vercel Env Vars မှ load လုပ်သည်"""

    # ── Telegram ──────────────────────────────────────────────────
    BOT_TOKEN: str  = os.environ.get("BOT_TOKEN", "")
    API_ID:    int  = int(os.environ.get("API_ID", "0") or "0")
    API_HASH:  str  = os.environ.get("API_HASH", "")

    # ── Admin ─────────────────────────────────────────────────────
    ADMIN_IDS: list[int] = [
        int(x.strip())
        for x in os.environ.get("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")

    # ── MongoDB ───────────────────────────────────────────────────
    MONGO_URI: str = os.environ.get("MONGO_URI", "")
    DB_NAME:   str = os.environ.get("DB_NAME", "telecms_db")

    # ── Webhook ───────────────────────────────────────────────────
    WEBHOOK_URL:    str = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")

    # ── Pyrogram StringSession ────────────────────────────────────
    STRING_SESSION: str = os.environ.get("STRING_SESSION", "")

    # ── Security ──────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-vercel-secrets")

    def validate(self) -> None:
        """
        Required settings စစ်ဆေးသည်။
        မပြည့်လျှင် ValueError raise ဆိုသည်။
        """
        missing = []
        if not self.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not self.API_ID:
            missing.append("API_ID")
        if not self.API_HASH:
            missing.append("API_HASH")
        if not self.MONGO_URI:
            missing.append("MONGO_URI")
        if not self.ADMIN_IDS:
            missing.append("ADMIN_IDS")
        if not self.WEBHOOK_URL:
            missing.append("WEBHOOK_URL")
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")


# Module-level singleton
config = Config()
