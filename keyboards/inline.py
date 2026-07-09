import math
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- CallbackData Factories ---

class MenuCallback(CallbackData, prefix="menu"):
    """
    Callback schema for general navigation (e.g., home, cart).
    """
    action: str

class CategoryCallback(CallbackData, prefix="cat"):
    """
    Callback schema for category selection and catalog navigation.
    """
    id: int
    page: int

class ProductCallback(CallbackData, prefix="prod"):
    """
    Callback schema for product details views.
    """
    id: int
    cat_id: int
    page: int

class OrdersCallback(CallbackData, prefix="myord"):
    """
    Callback schema for paginated 'My Orders' navigation.
    """
    page: int

# --- Inline Keyboard Builders ---

def get_home_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the Main Menu inline keyboard in Persian.
    - View Catalog button navigates to Categories with CategoryCallback.
    """
    builder = InlineKeyboardBuilder()

    # Left & Right split row using primary and secondary styles if compatible.
    # Utilizing custom style keyword arguments directly as supported in Bot API 9.4 models.
    builder.row(
        InlineKeyboardButton(
            text="🛍️ مشاهده کاتالوگ",
            callback_data=CategoryCallback(id=0, page=1).pack()
        )
    )
    builder.row(
        InlineKeyboardButton(text="📥 سفارشات من", callback_data=MenuCallback(action="my_orders").pack()),
        InlineKeyboardButton(text="👥 زیرمجموعه‌گیری", callback_data=MenuCallback(action="referrals").pack())
    )
    builder.row(
        InlineKeyboardButton(text="💼 کیف پول", callback_data=MenuCallback(action="wallet").pack()),
        InlineKeyboardButton(text="ℹ️ پشتیبانی", callback_data=MenuCallback(action="support").pack())
    )

    return builder.as_markup()

def get_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    """
    Generates dynamic list of categories with 'Back' button to home.
    """
    builder = InlineKeyboardBuilder()

    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {category['name']}",
                callback_data=CategoryCallback(id=category["id"], page=1).pack()
            )
        )

    # Return / Back button styled as 'danger' (Farsi: بازگشت)
    builder.row(
        InlineKeyboardButton(
            text="🔙 بازگشت به خانه",
            callback_data=MenuCallback(action="home").pack(),
            style="danger"
        )
    )

    return builder.as_markup()

def get_products_keyboard(products: list, category_id: int, current_page: int, total_count: int, limit: int = 5) -> InlineKeyboardMarkup:
    """
    Generates dynamic paginated list of products for a category.
    Limit of 5 products per page.
    Includes Next/Prev navigation and Back button to Categories.
    """
    builder = InlineKeyboardBuilder()

    # 1. Product list rows
    for product in products:
        stock_text = "🟢 موجود" if product["stock"] > 0 else "🔴 ناموجود"
        builder.row(
            InlineKeyboardButton(
                text=f"🔹 {product['name']} ({stock_text})",
                callback_data=ProductCallback(id=product["id"], cat_id=category_id, page=current_page).pack()
            )
        )

    # 2. Pagination controls row
    total_pages = math.ceil(total_count / limit)
    pagination_buttons = []

    if current_page > 1:
        pagination_buttons.append(
            InlineKeyboardButton(
                text="⬅️ صفحه قبل",
                callback_data=CategoryCallback(id=category_id, page=current_page - 1).pack(),
                style="secondary"
            )
        )
    if current_page < total_pages:
        pagination_buttons.append(
            InlineKeyboardButton(
                text="صفحه بعد ➡️",
                callback_data=CategoryCallback(id=category_id, page=current_page + 1).pack(),
                style="secondary"
            )
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    # 3. Back row
    back_button = InlineKeyboardButton(
        text="🔙 بازگشت به دسته‌بندی‌ها",
        callback_data=CategoryCallback(id=0, page=1).pack(),
        style="danger"
    )
    builder.row(back_button)

    return builder.as_markup()

def get_my_orders_keyboard(current_page: int, total_count: int) -> InlineKeyboardMarkup:
    """
    Generates inline keyboard for paginated 'My Orders' view.
    """
    builder = InlineKeyboardBuilder()

    pagination_buttons = []
    if current_page > 1:
        pagination_buttons.append(
            InlineKeyboardButton(
                text="⬅️ قبلی",
                callback_data=OrdersCallback(page=current_page - 1).pack()
            )
        )
    if current_page < total_count:
        pagination_buttons.append(
            InlineKeyboardButton(
                text="بعدی ➡️",
                callback_data=OrdersCallback(page=current_page + 1).pack()
            )
        )

    if pagination_buttons:
        builder.row(*pagination_buttons)

    builder.row(
        InlineKeyboardButton(
            text="🏠 بازگشت به خانه",
            callback_data=MenuCallback(action="home").pack(),
            style="danger"
        )
    )

    return builder.as_markup()

def get_product_detail_keyboard(product: dict, category_id: int, page: int) -> InlineKeyboardMarkup:
    """
    Keyboard for single product details.
    Includes Buy/Add to Cart styled as 'success' and Back styled as 'danger'.
    For negotiable/free products (price = 0), shows a 'Contact Support' button instead.
    """
    builder = InlineKeyboardBuilder()

    # Buy button or Support button
    if product["price"] == 0:
        buy_button = InlineKeyboardButton(
            text="📣 ارتباط با پشتیبانی و ثبت سفارش",
            callback_data=f"prod_support:{product['id']}",
            style="success"
        )
    else:
        buy_button = InlineKeyboardButton(
            text="🛒 افزودن به سبد خرید",
            callback_data=f"add_cart:{product['id']}",
            style="success"
        )
    builder.row(buy_button)

    # Back button
    back_button = InlineKeyboardButton(
        text="🔙 بازگشت",
        callback_data=CategoryCallback(id=category_id, page=page).pack(),
        style="danger"
    )
    builder.row(back_button)

    return builder.as_markup()
