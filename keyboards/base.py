from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import REQUIRED_CHANNEL

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the SPA style Store main menu inline keyboard.
    Using modern Telegram custom elements.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛍️ View Catalog", callback_data="view_catalog"),
            InlineKeyboardButton(text="📥 My Orders", callback_data="my_orders")
        ],
        [
            InlineKeyboardButton(text="💼 Wallet & Deposit", callback_data="wallet"),
            InlineKeyboardButton(text="👥 Referral Program", callback_data="referrals")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Support & Help", callback_data="support")
        ]
    ])

def get_join_channel_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Join Channel restriction keyboard.
    """
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}" if REQUIRED_CHANNEL.startswith("@") else "https://t.me/telegram"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=channel_url)],
        [InlineKeyboardButton(text="✅ I Joined", callback_data="check_joined")]
    ])
