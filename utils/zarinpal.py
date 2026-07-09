import logging
import aiohttp
from config import ZARINPAL_MERCHANT

logger = logging.getLogger(__name__)

ZARINPAL_REQUEST_URL = "https://payment.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = "https://payment.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_STARTPAY_URL = "https://payment.zarinpal.com/pg/StartPay/"

# If merchant is 36 characters long, it's a real merchant. Otherwise, fallback or support sandbox
IS_SANDBOX = len(ZARINPAL_MERCHANT) != 36 or ZARINPAL_MERCHANT.lower() == "sandbox"

if IS_SANDBOX:
    ZARINPAL_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    ZARINPAL_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
    ZARINPAL_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/"


async def create_zarinpal_payment(amount_toman: int, description: str, callback_url: str) -> str | None:
    """
    Sends a Payment Request to Zarinpal.
    Converts Tomans to Rials by multiplying by 10 as requested.
    Returns the redirect payment URL if successful, or None if failed.
    """
    amount_rial = amount_toman * 10
    payload = {
        "merchant_id": ZARINPAL_MERCHANT,
        "amount": amount_rial,
        "description": description,
        "callback_url": callback_url,
        "metadata": {
            "client": "Telegram Store Bot"
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ZARINPAL_REQUEST_URL, json=payload, headers=headers, timeout=15) as r:
                response_json = await r.json()

                # Check Zarinpal format: response has "data" and "errors"
                data = response_json.get("data")
                errors = response_json.get("errors")

                if data and data.get("code") == 100:
                    authority = data.get("authority")
                    if authority:
                        redirect_url = f"{ZARINPAL_STARTPAY_URL}{authority}"
                        logger.info(f"Zarinpal payment initiated. Authority: {authority}. URL: {redirect_url}")
                        return redirect_url

                logger.error(f"Zarinpal Request Failed. Response: {response_json}. Payload: {payload}")
                return None
    except Exception as e:
        logger.error(f"Exception during Zarinpal request: {e}")
        return None


async def verify_zarinpal_payment(amount_toman: int, authority: str) -> int | None:
    """
    Verifies a payment from Zarinpal using authority and original amount.
    Converts Tomans to Rials by multiplying by 10 as requested.
    Returns ref_id (int) if successful/verified, or None if failed.
    """
    amount_rial = amount_toman * 10
    payload = {
        "merchant_id": ZARINPAL_MERCHANT,
        "amount": amount_rial,
        "authority": authority
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ZARINPAL_VERIFY_URL, json=payload, headers=headers, timeout=15) as r:
                response_json = await r.json()

                data = response_json.get("data")
                errors = response_json.get("errors")

                # Code 100: Success, Code 101: Already Verified
                if data and data.get("code") in (100, 101):
                    ref_id = data.get("ref_id")
                    logger.info(f"Zarinpal payment verified successfully! Ref ID: {ref_id}")
                    return ref_id

                logger.error(f"Zarinpal Verification Failed. Response: {response_json}. Payload: {payload}")
                return None
    except Exception as e:
        logger.error(f"Exception during Zarinpal verification: {e}")
        return None
