"""
crypto.py — TeleCMS FileStore Pro
Deep link parameter HMAC signing & verification。
"""
import hmac
import hashlib
import base64
import logging

from config import config

logger = logging.getLogger(__name__)


def encode_content_id(content_id: str) -> str:
    """
    Content ID ကို tamper-proof deep link parameter အဖြစ် encode လုပ်သည်。
    Format: base64url(content_id:hmac_sha256[:12])

    Example:
        encode_content_id("507f1f77bcf86cd799439011")
        → "NTA3ZjFmNzdiY2Y4NmNkNzk5NDM5MDExOjFhMmIzYzRk"
    """
    try:
        key = config.SECRET_KEY.encode("utf-8")
        msg = content_id.encode("utf-8")
        # Python 3: hmac.new(key, msg, digestmod)
        signature = hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]

        combined = f"{content_id}:{signature}"
        encoded = base64.urlsafe_b64encode(combined.encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")  # URL-safe — = padding ဖယ်သည်

    except Exception as e:
        logger.error(f"encode_content_id error: {e}")
        return content_id


def decode_content_id(encoded: str) -> str | None:
    """
    Encoded deep link parameter ကို content_id ပြန်ရသည်。
    Signature မမှန်လျှင် None return ဆိုသည်。
    """
    try:
        encoded = encoded.strip()  # URL/whitespace strip
        # Base64 padding ပြန်ထည့်သည်
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding

        decoded_bytes = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        combined = decoded_bytes.decode("utf-8")

        if ":" not in combined:
            return None

        content_id, received_sig = combined.rsplit(":", 1)

        key = config.SECRET_KEY.encode("utf-8")
        msg = content_id.encode("utf-8")
        expected_sig = hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]

        # Timing-safe comparison
        if hmac.compare_digest(received_sig, expected_sig):
            return content_id

        logger.warning(f"Invalid signature for encoded param: {encoded[:20]}...")
        return None

    except Exception as e:
        logger.debug(f"decode_content_id error: {e}")
        return None
