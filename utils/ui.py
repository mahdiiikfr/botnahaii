import logging
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

async def edit_message_safely(
    event: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup = None
) -> Message | None:
    """
    Safely edits the text and keyboard of the single SPA message.
    Gracefully catches and suppresses aiogram's 'TelegramBadRequest'
    if the content is unmodified (prevents bot crashes on double-clicks).
    """
    target_msg = event if isinstance(event, Message) else event.message

    try:
        return await target_msg.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            # Suppress normal warning, this is expected in responsive fast double-clicks
            logger.debug("Suppressed: Message was unmodified.")
            return None
        logger.error(f"TelegramBadRequest error: {e}")
        raise e
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        return None

def format_breadcrumbs(path: str = "") -> str:
    """
    Formats the SPA Farsi RTL breadcrumbs navigation trail based on current menu depth.
    Hierarchy:
    - Home: 🏠 خانه
    - Categories: 🏠 خانه ➔ 📁 دسته‌بندی‌ها
    - Products: 🏠 خانه ➔ 📁 دسته‌بندی‌ها ➔ 🛍️ محصولات
    - Product Detail: 🏠 خانه ➔ 📁 دسته‌بندی‌ها ➔ 🛍️ محصولات ➔ 🔍 جزئیات
    """
    base = "<b>📌 مسیر شما:</b> "
    if path == "home" or not path:
        return f"{base}🏠 خانه"
    elif path == "categories":
        return f"{base}🏠 خانه ➔ 📁 دسته‌بندی‌ها"
    elif path == "products":
        return f"{base}🏠 خانه ➔ 📁 دسته‌بندی‌ها ➔ 🛍️ محصولات"
    elif path == "detail":
        return f"{base}🏠 خانه ➔ 📁 دسته‌بندی‌ها ➔ 🛍️ محصولات ➔ 🔍 جزئیات"
    return f"{base}🏠 خانه"

def format_currency(amount: int) -> str:
    """
    Formats integers with thousands separator using commas.
    Adds Farsi Currency suffix 'تومان'.
    e.g., 150000 -> ۱,۵۰۰,۰۰۰ تومان (using standard numbers or formatted strings).
    """
    # Use standard format representation with commas
    formatted = f"{amount:,}"
    # Translate standard digits to Persian digits for localized UX
    persian_digits = {"0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴", "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹"}
    for eng, per in persian_digits.items():
        formatted = formatted.replace(eng, per)
    return f"<b>{formatted} تومان</b>"
