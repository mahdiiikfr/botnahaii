import logging
import math
from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.db import DatabaseManager
from keyboards.inline import (
    MenuCallback,
    CategoryCallback,
    ProductCallback,
    OrdersCallback,
    get_home_keyboard,
    get_categories_keyboard,
    get_products_keyboard,
    get_product_detail_keyboard,
    get_my_orders_keyboard
)
from utils.ui import edit_message_safely, format_breadcrumbs, format_currency

logger = logging.getLogger(__name__)

router = Router(name="store_router")

@router.callback_query(MenuCallback.filter(F.action == "home"))
async def handle_home_menu(callback_query: CallbackQuery):
    """
    Handles navigation back to the main homepage menu.
    """
    breadcrumbs = format_breadcrumbs("home")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>👋 به فروشگاه پیشرفته ما خوش آمدید!</b>\n\n"
        "این یک ربات پیشرفته تک‌صفحه‌ای (SPA) است. "
        "تمامی منوها روی همین پیام بروزرسانی می‌شوند و چت شلوغ نمی‌شود.\n\n"
        "از منوی زیر می‌توانید محصولات را مشاهده کرده یا کیف پول خود را مدیریت کنید:"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_home_keyboard()
    )
    await callback_query.answer()

@router.callback_query(CategoryCallback.filter(F.id == 0))
async def handle_categories_list(callback_query: CallbackQuery, db: DatabaseManager):
    """
    Navigates to the Categories selection list view (Depth 1).
    """
    categories = await db.get_categories()
    breadcrumbs = format_breadcrumbs("categories")

    text = (
        f"{breadcrumbs}\n\n"
        "<b>📁 لطفاً یکی از دسته‌بندی‌های زیر را انتخاب کنید:</b>"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_categories_keyboard(categories)
    )
    await callback_query.answer()

@router.callback_query(CategoryCallback.filter(F.id > 0))
async def handle_category_products(
    callback_query: CallbackQuery,
    callback_data: CategoryCallback,
    db: DatabaseManager
):
    """
    Navigates to the Paginated Products list inside a category (Depth 2).
    Shows 5 products per page.
    """
    category_id = callback_data.id
    current_page = callback_data.page
    limit = 5

    # 1. Fetch active products
    active_products = await db.get_active_products(category_id)
    total_count = len(active_products)

    # 2. Slice products list for current page
    start_idx = (current_page - 1) * limit
    end_idx = start_idx + limit
    paginated_products = active_products[start_idx:end_idx]

    # Get Category Name to display
    categories = await db.get_categories()
    category_name = "دسته‌بندی"
    for cat in categories:
        if cat["id"] == category_id:
            category_name = cat["name"]
            break

    breadcrumbs = format_breadcrumbs("products")
    total_pages = max(1, math.ceil(total_count / limit))

    text = (
        f"{breadcrumbs}\n\n"
        f"<b>🛍️ محصولات دسته‌بندی {category_name}</b>\n"
        f"صفحه {current_page} از {total_pages}\n\n"
        "لطفاً جهت مشاهده جزئیات محصول، روی آن کلیک کنید:"
    )

    keyboard = get_products_keyboard(
        products=paginated_products,
        category_id=category_id,
        current_page=current_page,
        total_count=total_count,
        limit=limit
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=keyboard
    )
    await callback_query.answer()

@router.callback_query(ProductCallback.filter())
async def handle_product_details(
    callback_query: CallbackQuery,
    callback_data: ProductCallback,
    db: DatabaseManager
):
    """
    Displays single product detailed view (Depth 3).
    Displays title, description, price (formatted), and an 'Add to Cart' button.
    """
    product_id = callback_data.id
    cat_id = callback_data.cat_id
    page = callback_data.page

    # Fetch active products of this category to locate the target product details safely
    products = await db.get_active_products(cat_id)
    product = None
    for prod in products:
        if prod["id"] == product_id:
            product = prod
            break

    if not product:
        await callback_query.answer("⚠️ متأسفانه این محصول دیگر در دسترس نیست!", show_alert=True)
        return

    breadcrumbs = format_breadcrumbs("detail")
    formatted_price = format_currency(product["price"])
    stock_status = f"{product['stock']} عدد موجود" if product["stock"] > 0 else "❌ ناموجود"

    text = (
        f"{breadcrumbs}\n\n"
        f"<b>🔍 جزئیات محصول: {product['name']}</b>\n\n"
        f"📝 <b>توضیحات:</b>\n{product['description'] or 'توضیحاتی برای این محصول ثبت نشده است.'}\n\n"
        f"💰 <b>قیمت:</b> {formatted_price}\n"
        f"📦 <b>وضعیت موجودی:</b> {stock_status}"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_product_detail_keyboard(product, cat_id, page)
    )
    await callback_query.answer()

@router.callback_query(MenuCallback.filter(F.action == "my_orders"))
async def handle_my_orders_root(callback_query: CallbackQuery, db: DatabaseManager):
    """
    Renders the first page of the user's order history.
    """
    await handle_my_orders_page(callback_query, page=1, db=db)


@router.callback_query(OrdersCallback.filter())
async def handle_my_orders_navigation(callback_query: CallbackQuery, callback_data: OrdersCallback, db: DatabaseManager):
    """
    Navigates through paginated pages of order history.
    """
    await handle_my_orders_page(callback_query, page=callback_data.page, db=db)


async def handle_my_orders_page(callback_query: CallbackQuery, page: int, db: DatabaseManager):
    """
    Helper function to display details of the single order at index (page - 1).
    """
    user_id = callback_query.from_user.id
    total_orders = await db.get_total_user_orders_all_count(user_id)

    breadcrumbs = format_breadcrumbs("home")

    if total_orders == 0:
        text = (
            f"{breadcrumbs}\n\n"
            "<b>📥 سفارشات من</b>\n\n"
            "⚠️ شما هنوز هیچ سفارشی در این ربات ثبت نکرده‌اید!"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack(), style="danger")]
            ]
        )
        await edit_message_safely(callback_query, text, keyboard)
        await callback_query.answer()
        return

    # Fetch 1 order at the offset = page - 1
    orders = await db.get_user_orders_paginated(user_id, limit=1, offset=page - 1)
    if not orders:
        await callback_query.answer("⚠️ سفارش مورد نظر یافت نشد!", show_alert=True)
        return

    order = orders[0]

    # Map order status
    status_map = {
        "pending": "⏳ در انتظار بررسی مدیریت",
        "paid": "💳 پرداخت شده (در حال آماده‌سازی)",
        "delivered": "🟢 تحویل داده شده",
        "rejected": "❌ رد شده"
    }
    status_text = status_map.get(order["status"], order["status"])

    # Format order item
    if order["product_id"] is None:
        item_name = "💳 افزایش اعتبار کیف پول"
    else:
        item_name = f"🛍️ {order['product_name']}"

    formatted_amount = format_currency(order["amount"]) if order["amount"] else "نامشخص"

    # Format license / delivery info if any
    delivery_info = ""
    if order["status"] == "delivered" and order["product_id"] is not None:
        license_key = order["digital_data"] or "تحویل دستی (توسط مدیریت ارسال شده است)"
        delivery_info = (
            f"\n\n🗝️ <b>لایسنس / اطلاعات دیجیتال تحویل داده شده:</b>\n"
            f"<code>{license_key}</code>"
        )

    text = (
        f"{breadcrumbs}\n\n"
        f"<b>📥 سفارشات من (صفحه {page} از {total_orders})</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order['id']}\n"
        f"🏷️ <b>موضوع سفارش:</b> {item_name}\n"
        f"💰 <b>مبلغ تراکنش:</b> {formatted_amount}\n"
        f"🗓️ <b>تاریخ ثبت سفارش:</b> {order['date']}\n"
        f"⚙️ <b>وضعیت سفارش:</b> <b>{status_text}</b>"
        f"{delivery_info}"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = get_my_orders_keyboard(current_page=page, total_count=total_orders)

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=keyboard
    )
    await callback_query.answer()
