import logging
import math
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import edit_message_safely, format_breadcrumbs, format_currency
from utils.referrals import apply_referral_rewards
from config import ADMIN_ID, REQUIRED_CHANNEL

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

# --- FSM States ---
class AdminStates(StatesGroup):
    waiting_for_delivery_info = State()
    waiting_for_new_channel = State()
    waiting_for_cat_name = State()

    # Adding products
    waiting_for_prod_name = State()
    waiting_for_prod_price = State()
    waiting_for_prod_desc = State()
    waiting_for_prod_stock = State()
    waiting_for_prod_keys = State()

# --- Admin Authorization Check ---
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# --- COMMAND: /admin ---
@router.message(Command("admin"))
async def cmd_admin_panel(message: Message, state: FSMContext, db: DatabaseManager):
    """
    Command to open the professional Admin Panel (restricted to ADMIN_ID).
    """
    user_id = message.from_user.id
    if not is_admin(user_id):
        return  # Silently ignore non-admins (or auto-delete since they are not in FSM)

    await state.clear()

    # Automatically delete the typed /admin message to keep chat perfectly clean!
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete /admin message: {e}")

    text = (
        "<b>👑 پنل مدیریت پیشرفته ربات فروشگاه</b>\n\n"
        "به بخش مدیریت خوش آمدید! با استفاده از گزینه‌های زیر می‌توانید دسته‌بندی‌ها، محصولات، قیمت‌ها و محدودیت عضویت اجباری کانال را به صورت کاملاً پویا کنترل و ویرایش کنید 👇"
    )

    keyboard = get_admin_main_keyboard()
    await message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")


# --- Main Admin Keyboard ---
def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 مدیریت دسته‌بندی‌ها", callback_data="admin_manage_cats")],
        [InlineKeyboardButton(text="🛍️ مدیریت محصولات", callback_data="admin_manage_prods_cats")],
        [InlineKeyboardButton(text="📢 مدیریت کانال اجباری", callback_data="admin_manage_channel")],
        [InlineKeyboardButton(text="🏠 منوی اصلی ربات", callback_data=MenuCallback(action="home").pack())]
    ])


@router.callback_query(F.data == "admin_home")
async def handle_admin_home_callback(callback_query: CallbackQuery, state: FSMContext):
    """
    Returns to main admin home panel.
    """
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    await state.clear()
    text = (
        "<b>👑 پنل مدیریت پیشرفته ربات فروشگاه</b>\n\n"
        "به بخش مدیریت خوش آمدید! با استفاده از گزینه‌های زیر می‌توانید دسته‌بندی‌ها، محصولات، قیمت‌ها و محدودیت عضویت اجباری کانال را به صورت کاملاً پویا کنترل و ویرایش کنید 👇"
    )
    await edit_message_safely(callback_query, text, get_admin_main_keyboard())
    await callback_query.answer()


# ==========================================
# 📢 1. MANAGE FORCE JOIN CHANNEL
# ==========================================
@router.callback_query(F.data == "admin_manage_channel")
async def handle_admin_manage_channel(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    # Fetch dynamic channel from DB
    current_channel = await db.get_setting("required_channel", REQUIRED_CHANNEL)
    status_text = f"<code>{current_channel}</code>" if current_channel.lower() not in ("none", "no", "disable", "disabled", "off") else "❌ غیرفعال (بدون کانال)"

    text = (
        "<b>📢 مدیریت کانال عضویت اجباری</b>\n\n"
        f"📊 <b>کانال فعلی:</b> {status_text}\n\n"
        "جهت تغییر کانال یا غیرفعال کردن محدودیت عضویت، از دکمه‌های زیر استفاده کنید:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ تغییر کانال اجباری", callback_data="admin_change_channel")],
        [InlineKeyboardButton(text="❌ غیرفعال کردن عضویت اجباری", callback_data="admin_disable_channel")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin_home")]
    ])

    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "admin_disable_channel")
async def handle_admin_disable_channel(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    await db.set_setting("required_channel", "none")
    await callback_query.answer("✅ عضویت اجباری با موفقیت غیرفعال شد!", show_alert=True)
    await handle_admin_manage_channel(callback_query, db)


@router.callback_query(F.data == "admin_change_channel")
async def handle_admin_change_channel_prompt(callback_query: CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_new_channel)
    await state.update_data(admin_spa_msg_id=callback_query.message.message_id)

    text = (
        "<b>✍️ تغییر کانال عضویت اجباری</b>\n\n"
        "لطفاً آیدی کانال جدید را با علامت @ بنویسید و ارسال کنید:\n"
        "مثال: <code>@my_channel</code>\n\n"
        "⚠️ پیام شما بلافاصله پس از ارسال پاک خواهد شد."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="admin_manage_channel")]
    ])

    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.message(AdminStates.waiting_for_new_channel, F.text)
async def handle_admin_new_channel_submitted(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    new_chan = message.text.strip()

    # Simple validation
    if not new_chan.startswith("@") and not new_chan.startswith("-100"):
        new_chan = "@" + new_chan

    # Delete message
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete channel msg: {e}")

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    await state.clear()

    # Save to DB settings
    await db.set_setting("required_channel", new_chan)

    # Success edit
    text = (
        "<b>✅ کانال عضویت اجباری با موفقیت به‌روزرسانی شد!</b>\n\n"
        f"📢 کانال جدید: <code>{new_chan}</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_manage_channel")]
    ])
    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
         logger.error(f"Failed to update channel UI: {e}")


# ==========================================
# 📁 2. MANAGE CATEGORIES
# ==========================================
@router.callback_query(F.data == "admin_manage_cats")
async def handle_admin_manage_cats(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    categories = await db.get_categories()

    text = (
        "<b>📁 مدیریت دسته‌بندی‌های فروشگاه</b>\n\n"
        "در این بخش می‌توانید دسته‌بندی‌های موجود را مشاهده، اضافه یا حذف کنید:\n"
        "⚠️ <b>توجه:</b> حذف یک دسته‌بندی باعث حذف شدن تمام محصولات زیرمجموعه آن نیز خواهد شد!"
    )

    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {cat['name']}", callback_data=f"admin_view_cat_prods:{cat['id']}"),
            InlineKeyboardButton(text="🗑️ حذف", callback_data=f"admin_del_cat:{cat['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ افزودن دسته‌بندی جدید", callback_data="admin_add_cat")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به خانه مدیریتی", callback_data="admin_home")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "admin_add_cat")
async def handle_admin_add_cat_prompt(callback_query: CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_cat_name)
    await state.update_data(admin_spa_msg_id=callback_query.message.message_id)

    text = (
        "<b>➕ افزودن دسته‌بندی جدید</b>\n\n"
        "✍️ لطفاً نام دسته‌بندی جدید را بنویسید و ارسال کنید:\n"
        "مثال: <code>اکانت‌های نتفلیکس 🎬</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="admin_manage_cats")]
    ])

    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.message(AdminStates.waiting_for_cat_name, F.text)
async def handle_admin_cat_name_submitted(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    cat_name = message.text.strip()
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete: {e}")

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    await state.clear()

    # Insert into DB
    async with db._conn.cursor() as cursor:
        await cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?);", (cat_name,))
        await db._conn.commit()

    text = f"<b>✅ دسته‌بندی «{cat_name}» با موفقیت اضافه شد!</b>"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_manage_cats")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error edit text: {e}")


@router.callback_query(F.data.startswith("admin_del_cat:"))
async def handle_admin_del_cat(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    cat_id = int(callback_query.data.split(":")[1])

    async with db._conn.cursor() as cursor:
        await cursor.execute("DELETE FROM categories WHERE id = ?;", (cat_id,))
        await db._conn.commit()

    await callback_query.answer("✅ دسته‌بندی با موفقیت حذف شد!", show_alert=True)
    await handle_admin_manage_cats(callback_query, db)


# ==========================================
# 🛍️ 3. MANAGE PRODUCTS (SELECTOR CAT)
# ==========================================
@router.callback_query(F.data == "admin_manage_prods_cats")
async def handle_admin_manage_prods_cats(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    categories = await db.get_categories()

    text = (
        "<b>🛍️ مدیریت محصولات فروشگاه</b>\n\n"
        "لطفاً جهت مدیریت و ویرایش محصولات، دسته‌بندی مربوطه را انتخاب کنید:"
    )

    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {cat['name']}", callback_data=f"admin_view_cat_prods:{cat['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به خانه مدیریتی", callback_data="admin_home")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin_view_cat_prods:"))
async def handle_admin_view_cat_prods(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    cat_id = int(callback_query.data.split(":")[1])

    products = await db.get_active_products(cat_id)

    # Fetch Category name
    async with db._conn.execute("SELECT name FROM categories WHERE id = ?;", (cat_id,)) as cursor:
        cat_row = await cursor.fetchone()
    cat_name = cat_row["name"] if cat_row else "نامشخص"

    text = (
        f"<b>🛍️ مدیریت محصولات دسته‌بندی {cat_name}</b>\n\n"
        "در این بخش می‌توانید محصولات این دسته‌بندی را اضافه، ویرایش یا حذف نمایید:"
    )

    buttons = []
    for prod in products:
        buttons.append([
            InlineKeyboardButton(text=f"🔹 {prod['name']} ({format_currency(prod['price'])})", callback_data=f"admin_edit_prod_detail:{prod['id']}"),
            InlineKeyboardButton(text="🗑️ حذف", callback_data=f"admin_del_prod:{prod['id']}:{cat_id}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ افزودن محصول جدید", callback_data=f"admin_add_prod_start:{cat_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به دسته‌بندی‌ها", callback_data="admin_manage_prods_cats")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin_del_prod:"))
async def handle_admin_delete_product(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    parts = callback_query.data.split(":")
    prod_id = int(parts[1])
    cat_id = int(parts[2])

    async with db._conn.cursor() as cursor:
        await cursor.execute("DELETE FROM products WHERE id = ?;", (prod_id,))
        await db._conn.commit()

    await callback_query.answer("✅ محصول با موفقیت حذف شد!", show_alert=True)
    await handle_admin_view_cat_prods(callback_query, db)


# --- 🛍️ PRODUCT ADD FSM FLOW ---
@router.callback_query(F.data.startswith("admin_add_prod_start:"))
async def handle_admin_add_prod_start(callback_query: CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    cat_id = int(callback_query.data.split(":")[1])

    await state.set_state(AdminStates.waiting_for_prod_name)
    await state.update_data(
        add_prod_cat_id=cat_id,
        admin_spa_msg_id=callback_query.message.message_id
    )

    text = (
        "<b>➕ افزودن محصول جدید - مرحله ۱ از ۵</b>\n\n"
        "✍️ لطفاً <b>نام محصول</b> را وارد و ارسال کنید:\n"
        "مثال: <code>اکانت نتفلیکس پرمیوم</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


@router.message(AdminStates.waiting_for_prod_name, F.text)
async def handle_add_prod_name(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    name = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    cat_id = state_data["add_prod_cat_id"]

    await state.update_data(add_prod_name=name)
    await state.set_state(AdminStates.waiting_for_prod_price)

    text = (
        f"<b>🛒 نام ثبت شده:</b> {name}\n\n"
        "<b>💰 مرحله ۲ از ۵:</b>\n"
        "لطفاً <b>قیمت محصول (به تومان)</b> را بنویسید و ارسال کنید:\n"
        "<i>عدد وارد شده باید صرفاً عدد انگلیسی بدون حروف یا کاما باشد. برای محصولات رایگان یا توافقی عدد 0 را وارد کنید.</i>\n\n"
        "مثال: <code>150000</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


@router.message(AdminStates.waiting_for_prod_price, F.text)
async def handle_add_prod_price(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    raw_price = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    cat_id = state_data["add_prod_cat_id"]

    try:
        price = int(raw_price)
        if price < 0:
            raise ValueError()
    except ValueError:
        # Prompt price error
        text = (
            "<b>⚠️ خطای قالب قیمت!</b>\n\n"
            "لطفاً قیمت را فقط به صورت عدد مثبت بزرگتر یا مساوی صفر تایپ و ارسال کنید:\n"
            "مثال: <code>150000</code>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
        ])
        try:
            await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass
        return

    await state.update_data(add_prod_price=price)
    await state.set_state(AdminStates.waiting_for_prod_desc)

    text = (
        f"<b>🛒 قیمت ثبت شده:</b> {format_currency(price)}\n\n"
        "<b>📝 مرحله ۳ از ۵:</b>\n"
        "لطفاً <b>توضیحات محصول</b> را بنویسید و ارسال کنید:\n"
        "مثال: <code>اکانت پرمیوم ۱ ماهه نتفلیکس با کیفیت Ultra HD</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


@router.message(AdminStates.waiting_for_prod_desc, F.text)
async def handle_add_prod_desc(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    desc = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    cat_id = state_data["add_prod_cat_id"]

    await state.update_data(add_prod_desc=desc)
    await state.set_state(AdminStates.waiting_for_prod_stock)

    text = (
        "<b>📦 مرحله ۴ از ۵:</b>\n"
        "لطفاً <b>موجودی محصول (تعداد)</b> را ارسال کنید (عدد مثبت):\n"
        "مثال: <code>50</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


@router.message(AdminStates.waiting_for_prod_stock, F.text)
async def handle_add_prod_stock(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    raw_stock = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    cat_id = state_data["add_prod_cat_id"]

    try:
        stock = int(raw_stock)
        if stock < 0:
            raise ValueError()
    except ValueError:
        text = (
            "<b>⚠️ خطای قالب موجودی!</b>\n\n"
            "لطفاً موجودی را صرفاً به صورت عدد مثبت (مثلاً 50) تایپ و ارسال کنید:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
        ])
        try:
            await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass
        return

    await state.update_data(add_prod_stock=stock)
    await state.set_state(AdminStates.waiting_for_prod_keys)

    text = (
        "<b>🗝️ مرحله ۵ از ۵:</b>\n"
        "لطفاً <b>لایسنس یا اطلاعات پیش‌فرض تحویل خودکار</b> (یا کلمه 'دستی' برای تحویل دستی) را بنویسید و ارسال کنید:\n"
        "مثال: <code>LICENSE-KEY-123</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


@router.message(AdminStates.waiting_for_prod_keys, F.text)
async def handle_add_prod_keys(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    keys = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    spa_msg_id = state_data["admin_spa_msg_id"]
    cat_id = state_data["add_prod_cat_id"]
    name = state_data["add_prod_name"]
    price = state_data["add_prod_price"]
    desc = state_data["add_prod_desc"]
    stock = state_data["add_prod_stock"]

    await state.clear()

    # Save to SQLite
    async with db._conn.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1);
            """,
            (cat_id, name, desc, price, stock, keys)
        )
        await db._conn.commit()

    text = (
        "<b>✅ محصول با موفقیت ایجاد گردید!</b>\n\n"
        f"🛍️ <b>نام محصول:</b> {name}\n"
        f"💰 <b>قیمت:</b> {format_currency(price)}\n"
        f"📦 <b>موجودی:</b> {stock} عدد\n"
        f"🗝️ <b>مشخصات تحویل:</b> <code>{keys}</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به لیست محصولات", callback_data=f"admin_view_cat_prods:{cat_id}")]
    ])

    try:
        await bot.edit_message_text(chat_id=message.from_user.id, message_id=spa_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass


# ==========================================
# ✍️ PRODUCT DETAILS VIEW & EDIT
# ==========================================
@router.callback_query(F.data.startswith("admin_edit_prod_detail:"))
async def handle_admin_edit_prod_detail(callback_query: CallbackQuery, db: DatabaseManager):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⚠️ عدم دسترسی!", show_alert=True)
        return

    prod_id = int(callback_query.data.split(":")[1])

    # Fetch product details
    async with db._conn.execute(
        "SELECT id, category_id, name, description, price, stock, digital_data FROM products WHERE id = ?;", (prod_id,)
    ) as cursor:
        prod = await cursor.fetchone()

    if not prod:
        await callback_query.answer("⚠️ محصول پیدا نشد!", show_alert=True)
        return

    text = (
        f"<b>🔍 جزئیات محصول: {prod['name']}</b>\n\n"
        f"🏷️ <b>نام:</b> {prod['name']}\n"
        f"💰 <b>قیمت:</b> {format_currency(prod['price'])}\n"
        f"📦 <b>موجودی:</b> {prod['stock']} عدد\n"
        f"📝 <b>توضیحات:</b>\n{prod['description'] or 'بدون توضیح'}\n"
        f"🗝️ <b>لایسنس / مشخصات پیش‌فرض:</b> <code>{prod['digital_data'] or 'ندارد'}</code>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به لیست محصولات", callback_data=f"admin_view_cat_prods:{prod['category_id']}")]
    ])

    await edit_message_safely(callback_query, text, keyboard)
    await callback_query.answer()


# ==========================================
# 💸 RECENT ORDER APPROVALS & REJECTIONS
# ==========================================
@router.callback_query(F.data.startswith("admin_approve:"))
async def handle_admin_approval(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot, state: FSMContext):
    """
    Handles admin's 'Approve Payment' callback query button click.
    Checks order parameters:
    1. If product_id IS NULL (None): It is a Wallet Deposit.
       - Increment user's wallet balance by order's recorded amount.
       - Send a successful wallet recharge notification in Farsi.
       - Update order status to delivered.
    2. If product_id IS NOT NULL: It is a standard product purchase.
       - Do not deliver instantly. Ask Admin to type and send custom delivery credentials.
       - Transition admin to AdminStates.waiting_for_delivery_info.
    Updates Admin interface dynamically to prevent double-clicks.
    """
    order_id = int(callback_query.data.split(":")[1])

    # Fetch order record
    async with db._conn.execute(
        "SELECT id, user_id, product_id, amount, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد یا حذف شده است!", show_alert=True)
        return

    if order["status"] in ("delivered", "rejected"):
        await callback_query.answer("⚠️ این تراکنش قبلاً بررسی گردیده است!", show_alert=True)
        return

    # Process based on order type (Deposit vs Product Purchase)
    if order["product_id"] is None:
        # --- A. WALLET DEPOSIT ORDER ---
        deposit_amount = order["amount"] or 0

        # 1. Update order status in DB to delivered
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
            await db._conn.commit()

        # 2. Add amount to user's wallet balance
        await db.update_user_balance(order["user_id"], deposit_amount)

        # 3. Update Admin Interface
        await _clean_admin_ui(callback_query, order_id, is_approved=True)
        await callback_query.answer("✅ افزایش اعتبار حساب کاربر با موفقیت تایید و اعمال شد.")

        # 4. Notify Customer inside their Telegram Chat (Farsi, SPA style)
        breadcrumbs = format_breadcrumbs("home")
        recharge_text = (
            f"{breadcrumbs}\n\n"
            f"<b>🎉 اعتبار حساب شما افزایش یافت!</b>\n\n"
            f"📦 <b>شناسه سفارش شارژ:</b> #{order_id}\n"
            f"💰 <b>مبلغ افزوده شده:</b> {format_currency(deposit_amount)}\n\n"
            "تراکنش واریزی شما تایید گردید و موجودی کیف پول شما با موفقیت به روزرسانی شد.\n"
            "هم‌اکنون می‌توانید از محل موجودی اقدام به تهیه خدمات نمایید."
        )

        back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
        ])

        try:
            await bot.send_message(
                chat_id=order["user_id"],
                text=recharge_text,
                reply_markup=back_home_keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Delivered successful recharge notify to user {order['user_id']}.")
        except TelegramForbiddenError:
            logger.warning(f"Could not notify customer {order['user_id']} of deposit approval: User blocked the bot.")
        except TelegramAPIError as e:
            logger.error(f"Failed to notify customer {order['user_id']} of deposit approval: {e}")

    else:
        # --- B. STANDARD PRODUCT PURCHASE ---
        # Instead of delivering dummy/placeholder digital_data immediately,
        # ask the Admin to type and send custom delivery details.
        await state.set_state(AdminStates.waiting_for_delivery_info)
        await state.update_data(
            approve_order_id=order_id,
            approve_user_id=order["user_id"],
            approve_admin_msg_id=callback_query.message.message_id,
            approve_admin_caption=callback_query.message.text or callback_query.message.caption or ""
        )

        # Remove decision buttons and show input prompt
        await callback_query.message.edit_reply_markup(reply_markup=None)

        prompt_text = (
            f"<b>✍️ ارسال اطلاعات تحویل سفارش #{order_id}:</b>\n\n"
            f"لطفاً لایسنس، مشخصات کاربری اکانت، یا اطلاعات تحویل این سفارش را تایپ و ارسال کنید تا مستقیماً برای کاربر فرستاده شود:\n"
        )

        try:
            if callback_query.message.caption:
                await callback_query.message.edit_caption(
                    caption=prompt_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="cancel_admin_approve")]
                    ]),
                    parse_mode="HTML"
                )
            else:
                await callback_query.message.edit_text(
                    text=prompt_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="cancel_admin_approve")]
                    ]),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Failed to display admin delivery input prompt: {e}")
        await callback_query.answer()


@router.callback_query(F.data == "cancel_admin_approve")
async def handle_cancel_admin_approve(callback_query: CallbackQuery, state: FSMContext):
    """
    Cancels the admin custom delivery info input and restores original decision buttons.
    """
    state_data = await state.get_data()
    order_id = state_data.get("approve_order_id")
    original_caption = state_data.get("approve_admin_caption", "اعلان سفارش جدید")

    await state.clear()

    if not order_id:
        await callback_query.message.delete()
        return

    from keyboards.admin import get_admin_decision_keyboard
    try:
        if callback_query.message.caption:
            await callback_query.message.edit_caption(
                caption=original_caption,
                reply_markup=get_admin_decision_keyboard(order_id),
                parse_mode="HTML"
            )
        else:
            await callback_query.message.edit_text(
                text=original_caption,
                reply_markup=get_admin_decision_keyboard(order_id),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to restore admin decision interface: {e}")
    await callback_query.answer("عملیات لغو گردید.")


@router.message(AdminStates.waiting_for_delivery_info, F.text)
async def handle_admin_delivery_submitted(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    """
    Processes Admin's text input as custom delivery credentials.
    - Saves details inside order record in the database.
    - Sets order status as delivered.
    - Decrements stock from products table.
    - Delivers custom keys/text to customer.
    - Triggers 10% referral cashback if there's an inviter.
    - Deletes Admin's message instantly.
    """
    delivery_details = message.text.strip()

    # Get state context
    state_data = await state.get_data()
    order_id = state_data["approve_order_id"]
    user_id = state_data["approve_user_id"]
    admin_spa_msg_id = state_data["approve_admin_msg_id"]
    original_caption = state_data.get("approve_admin_caption", "")

    # Clear state and delete typing message immediately
    await state.clear()
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete admin typing message: {e}")

    # Fetch order record
    async with db._conn.execute(
        "SELECT product_id FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await bot.send_message(chat_id=message.from_user.id, text="⚠️ خطا: سفارش یافت نشد!")
        return

    # 1. Update delivery data and status to delivered in DB
    await db.update_order_delivery_data(order_id, delivery_details)
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin interface cleanly to show approved status
    status_suffix = f"\n\n<b>وضعیت: ✅ تأیید شد و تحویل گردید</b>\n<b>اطلاعات تحویلی:</b>\n<code>{delivery_details}</code>"
    updated_text = original_caption + status_suffix
    try:
        try:
            await bot.edit_message_caption(
                chat_id=message.from_user.id,
                message_id=admin_spa_msg_id,
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        except Exception:
            await bot.edit_message_text(
                chat_id=message.from_user.id,
                message_id=admin_spa_msg_id,
                text=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to update Admin UI with delivery info: {e}")

    # 3. Fetch product details
    async with db._conn.execute(
        "SELECT name, price FROM products WHERE id = ?;", (order["product_id"],)
    ) as cursor:
        product = await cursor.fetchone()

    # 4. Deliver digital content cleanly to customer
    breadcrumbs = format_breadcrumbs("home")
    delivery_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 سفارش شما آماده شد و تحویل گردید!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول خریداری شده:</b> {product['name'] if product else 'خدمات وب و پشتیبانی'}\n\n"
        f"🗝️ <b>مشخصات / اطلاعات تحویل ارسال شده توسط مدیریت:</b>\n"
        f"<code>{delivery_details}</code>\n\n"
        "از خرید شما صمیمانه سپاسگزاریم! جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=delivery_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Delivered order keys #{order_id} directly to client {user_id}.")
    except TelegramForbiddenError:
        logger.warning(f"Could not deliver keys for order #{order_id}: User blocked the bot.")
    except TelegramAPIError as e:
        logger.error(f"Failed to deliver keys for order #{order_id} due to api error: {e}")

    # 5. Decrement stock
    if order["product_id"] is not None:
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE products SET stock = MAX(0, stock - 1) WHERE id = ?;", (order["product_id"],))
            await db._conn.commit()

    # 6. Trigger 10% Referral commission logic if applicable
    user_row = await db.get_user(user_id)
    if user_row and product:
        await apply_referral_rewards(db, bot, user_row, product)


@router.callback_query(F.data.startswith("admin_reject:"))
async def handle_admin_rejection(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Reject Payment' callback query button click.
    Updates DB order status to 'rejected'.
    Notifies customer that transaction was rejected.
    If the customer had paid using Wallet/Online simulation (status was 'paid'),
    refunds the deducted amount back to their wallet balance automatically.
    Cleans admin UI to prevent double-clicks.
    """
    order_id = int(callback_query.data.split(":")[1])

    async with db._conn.execute(
        "SELECT id, user_id, amount, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد!", show_alert=True)
        return

    if order["status"] == "rejected":
        await callback_query.answer("⚠️ این سفارش قبلاً رد شده است!", show_alert=True)
        await _clean_admin_ui(callback_query, order_id, is_approved=False)
        return

    # Check if we should refund (Wallet/Gateway payments had status 'paid' originally)
    refunded = False
    refund_text = ""
    if order["status"] == "paid" and order["amount"] and order["amount"] > 0:
        await db.update_user_balance(order["user_id"], order["amount"])
        refunded = True
        refund_text = f"\n\n💰 <b>بازگشت وجه:</b> مبلغ {format_currency(order['amount'])} با موفقیت به موجودی کیف پول شما برگشت داده شد."

    # 1. Update order status to rejected in database
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin Interface
    await _clean_admin_ui(callback_query, order_id, is_approved=False)
    await callback_query.answer("❌ تراکنش با موفقیت رد شد.")

    # 3. Notify Customer of rejection (Farsi)
    breadcrumbs = format_breadcrumbs("home")
    rejection_text = (
        f"{breadcrumbs}\n\n"
        f"<b>⚠️ سفارش شما رد شد!</b>\n\n"
        f"📦 <b>شناسه تراکنش:</b> #{order_id}\n\n"
        "متأسفانه واریز رسید ثبت شده یا سفارش شما مورد تأیید قرار نگرفت.\n"
        "خواهشمند است اطلاعات تراکنش خود را مجدداً بررسی کرده یا در صورت لزوم با بخش پشتیبانی در ارتباط باشید."
        f"{refund_text}\n\n"
        "جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید:"
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.send_message(
            chat_id=order["user_id"],
            text=rejection_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Dispatched rejection notification for order #{order_id} to user {order['user_id']}.")
    except TelegramForbiddenError:
        logger.warning(f"Failed to deliver rejection notify for order #{order_id}: User blocked the bot.")
    except TelegramAPIError as e:
        logger.error(f"Failed to deliver rejection notify for order #{order_id} due to api error: {e}")


async def _clean_admin_ui(callback_query: CallbackQuery, order_id: int, is_approved: bool):
    """
    Cleans up the admin's action matrix to prevent double clicks.
    Edits original layout caption or text, appending the static status, and removes inline keyboards.
    """
    original_text = callback_query.message.text or callback_query.message.caption or ""

    status_suffix = "\n\n<b>وضعیت: ✅ تأیید گردید</b>" if is_approved else "\n\n<b>وضعیت: ❌ تراکنش رد شد</b>"
    updated_text = original_text + status_suffix

    try:
        if callback_query.message.caption:
            await callback_query.message.edit_caption(
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            await callback_query.message.edit_text(
                text=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to clean admin interface for order #{order_id}: {e}")
