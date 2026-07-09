from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import REQUIRED_CHANNEL

def get_join_channel_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Join Channel restriction keyboard in Persian.
    """
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}" if REQUIRED_CHANNEL.startswith("@") else "https://t.me/telegram"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عضویت در کانال", url=channel_url)],
        [InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_joined")]
    ])
