import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import edit_message_safely, format_breadcrumbs

logger = logging.getLogger(__name__)

router = Router(name="referral_router")

@router.callback_query(MenuCallback.filter(F.action == "referrals"))
async def handle_referral_panel(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Renders user's Referral system interface in Farsi (SPA styled).
    Queries bot username dynamically and prints a clean, copyable deep link invitation.
    """
    user_id = callback_query.from_user.id

    # 1. Fetch user data to obtain referral code
    user_data = await db.get_user(user_id)
    if not user_data:
        await callback_query.answer("⚠️ خطا: اطلاعات کاربری یافت نشد!", show_alert=True)
        return

    referral_code = user_data["referral_code"]

    # 2. Query bot username dynamically (portable and safe)
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    invite_url = f"https://t.me/{bot_username}?start={referral_code}"

    # 3. Retrieve sub-users count
    invited_count = await db.get_invited_users_count(user_id)

    breadcrumbs = format_breadcrumbs("home")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>🤝 برنامه زیرمجموعه‌گیری و درآمدزایی</b>\n\n"
        "با دعوت از دوستان خود به ربات ما، <b>۱۰٪ از مبلغ هر خرید</b> آن‌ها را به عنوان پورسانت به صورت مستقیم درون کیف پول خود دریافت کنید! 😍💰\n\n"
        f"📊 <b>تعداد دعوت‌های موفق شما:</b> {invited_count} نفر\n\n"
        "🔗 <b>لینک دعوت اختصاصی شما:</b>\n"
        f"<code>{invite_url}</code>\n\n"
        "✨ جهت کپی کردن لینک دعوت، کافیست روی مستطیل بالا ضربه بزنید."
    )

    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 بازگشت به حساب کاربری", callback_data=MenuCallback(action="wallet").pack())],
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=back_keyboard
    )
    await callback_query.answer()
