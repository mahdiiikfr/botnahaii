from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_admin_decision_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Returns an interactive decision matrix inline keyboard for admins.
    Uses Telegram Bot API 9.4 styles: success for approval, danger for rejection.
    """
    builder = InlineKeyboardBuilder()

    approve_button = InlineKeyboardButton(
        text="✅ تایید پرداخت",
        callback_data=f"admin_approve:{order_id}",
        style="success"
    )

    reject_button = InlineKeyboardButton(
        text="❌ رد پرداخت",
        callback_data=f"admin_reject:{order_id}",
        style="danger"
    )

    builder.row(approve_button, reject_button)
    return builder.as_markup()
