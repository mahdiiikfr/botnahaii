import logging
import math
from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.db import DatabaseManager
from keyboards.inline import (
    MenuCallback,
    CategoryCallback,
    ProductCallback,
    get_home_keyboard,
    get_categories_keyboard,
    get_products_keyboard,
    get_product_detail_keyboard
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

@router.callback_query(F.data.startswith("add_cart:"))
async def handle_add_to_cart(callback_query: CallbackQuery, db: DatabaseManager):
    """
    Triggers when user clicks 'Add to Cart'.
    Provides instant Persian feedback via show_alert=False popup.
    """
    product_id_str = callback_query.data.split(":")[1]

    try:
        product_id = int(product_id_str)
    except ValueError:
        await callback_query.answer("⚠️ شناسه محصول نامعتبر است!", show_alert=True)
        return

    # In Phase 3, we just simulate adding to cart with a success alert popup
    # Later phases will handle real basket storage.
    alert_text = "🛒 محصول با موفقیت به سبد خرید شما اضافه شد! در مراحل بعدی می‌توانید خرید خود را نهایی کنید."
    await callback_query.answer(text=alert_text, show_alert=False)
