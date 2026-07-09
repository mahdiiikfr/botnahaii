import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
from config import BOT_TOKEN, DB_PATH, WEB_PORT
from database.db import DatabaseManager
from middlewares.db import DbMiddleware
from middlewares.throttling import ThrottlingMiddleware
from middlewares.force_join import ForceJoinMiddleware
from handlers.base import router as base_router
from handlers.store import router as store_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router
from handlers.wallet import router as wallet_router
from handlers.referral import router as referral_router
from handlers.support import router as support_router
from utils.backup import run_backup_scheduler
from utils.zarinpal import verify_zarinpal_payment
from keyboards.inline import MenuCallback
from utils.ui import format_breadcrumbs, format_currency
from utils.admin_logs import send_order_log_to_admin

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def handle_zarinpal_callback(request: web.Request):
    db = request.app['db']
    bot = request.app['bot']

    params = request.query
    order_id_str = params.get("order_id")
    authority = params.get("Authority")
    status = params.get("Status")

    failure_html = """
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>خطا در پرداخت</title>
        <style>
            body { font-family: Tahoma, sans-serif; text-align: center; padding: 50px; background-color: #fce4ec; color: #c2185b; }
            .container { border: 1px solid #c2185b; padding: 30px; display: inline-block; background: #fff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            h2 { margin-top: 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>❌ تراکنش ناموفق یا لغو شده</h2>
            <p>پرداخت شما ناموفق بود یا توسط شما لغو شد. در صورتی که وجه از حساب شما کسر شده باشد، به زودی عودت داده می‌شود.</p>
            <p>لطفاً به ربات تلگرام بازگردید.</p>
        </div>
    </body>
    </html>
    """

    if not order_id_str or not authority:
        return web.Response(text=failure_html, content_type='text/html')

    try:
        order_id = int(order_id_str)
    except ValueError:
        return web.Response(text=failure_html, content_type='text/html')

    # Fetch order from DB
    async with db._conn.execute(
        "SELECT id, user_id, product_id, amount, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        return web.Response(text=failure_html, content_type='text/html')

    # If already verified
    if order["status"] in ("paid", "delivered"):
        success_already_html = f"""
        <!DOCTYPE html>
        <html lang="fa" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>پرداخت ثبت شده</title>
            <style>
                body {{ font-family: Tahoma, sans-serif; text-align: center; padding: 50px; background-color: #e8f5e9; color: #2e7d32; }}
                .container {{ border: 1px solid #2e7d32; padding: 30px; display: inline-block; background: #fff; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>✅ تراکنش قبلاً تأیید گردیده است</h2>
                <p>سفارش شماره #{order_id} قبلاً پرداخت شده و در حال پردازش است. لطفاً به ربات تلگرام برگردید.</p>
            </div>
        </body>
        </html>
        """
        return web.Response(text=success_already_html, content_type='text/html')

    if status != "OK":
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?;", (order_id,))
            await db._conn.commit()
        return web.Response(text=failure_html, content_type='text/html')

    # Amount in Tomans
    amount_toman = order["amount"] or 0

    # Securely verify payment on official Zarinpal servers
    ref_id = await verify_zarinpal_payment(amount_toman, authority)

    if not ref_id:
        return web.Response(text=failure_html, content_type='text/html')

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    user_id = order["user_id"]
    user_row = await db.get_user(user_id)
    username = user_row["username"] if user_row else "نامشخص"

    if order["product_id"] is None:
        # --- WALLET DEPOSIT ---
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'delivered', payment_receipt = ? WHERE id = ?;", (str(ref_id), order_id))
            await db._conn.commit()

        await db.update_user_balance(user_id, amount_toman)

        breadcrumbs = format_breadcrumbs("home")
        success_text = (
            f"{breadcrumbs}\n\n"
            f"<b>🎉 افزایش اعتبار کیف پول با موفقیت انجام شد!</b>\n\n"
            f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
            f"💰 <b>مبلغ افزوده شده:</b> {format_currency(amount_toman)}\n"
            f"🔑 <b>کد پیگیری تراکنش (بانک):</b> <code>{ref_id}</code>\n\n"
            "موجودی کیف پول شما بلافاصله به‌روزرسانی گردید. هم‌اکنون می‌توانید اقدام به خرید خدمات فرمایید."
        )
        back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
        ])
        try:
            await bot.send_message(chat_id=user_id, text=success_text, reply_markup=back_home_keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify user of wallet deposit: {e}")

        price_text = format_currency(amount_toman)
        await send_order_log_to_admin(
            bot=bot,
            order_id=order_id,
            user_id=user_id,
            username=username,
            product_name="افزایش اعتبار کیف پول (زرین‌پال)",
            price_text=price_text,
            method_text=f"درگاه مستقیم زرین‌پال (Ref ID: {ref_id})"
        )
    else:
        # --- PRODUCT PURCHASE ---
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'paid', payment_receipt = ? WHERE id = ?;", (str(ref_id), order_id))
            await db._conn.commit()

        async with db._conn.execute(
            "SELECT name FROM products WHERE id = ?;", (order["product_id"],)
        ) as cursor:
            product_row = await cursor.fetchone()
        product_name = product_row["name"] if product_row else "محصول فروشگاه"

        breadcrumbs = format_breadcrumbs("home")
        pending_text = (
            f"{breadcrumbs}\n\n"
            f"<b>🎉 پرداخت آنلاین شما با موفقیت تأیید شد!</b>\n\n"
            f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
            f"🛍️ <b>محصول خریداری شده:</b> {product_name}\n"
            f"💰 <b>مبلغ تراکنش:</b> {format_currency(amount_toman)}\n"
            f"🔑 <b>کد پیگیری تراکنش (بانک):</b> <code>{ref_id}</code>\n\n"
            "سفارش شما با موفقیت پرداخت گردید و در صف بررسی مدیریت قرار گرفت. به محض تایید و تحویل کالا، مشخصات تحویل برای شما ارسال خواهد شد."
        )
        back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
        ])
        try:
            await bot.send_message(chat_id=user_id, text=pending_text, reply_markup=back_home_keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify user of product purchase: {e}")

        price_text = format_currency(amount_toman)
        await send_order_log_to_admin(
            bot=bot,
            order_id=order_id,
            user_id=user_id,
            username=username,
            product_name=product_name,
            price_text=price_text,
            method_text=f"درگاه مستقیم زرین‌پال (Ref ID: {ref_id})"
        )

    success_html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>پرداخت با موفقیت انجام شد</title>
    </head>
    <body style="font-family: Tahoma, sans-serif; text-align: center; padding: 50px; background-color: #f7f9fa; color: #333;">
        <div style="background: #ffffff; padding: 40px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 15px rgba(0,0,0,0.1); max-width: 500px; width: 100%;">
            <div style="color: #4CAF50; font-size: 64px; margin-bottom: 10px;">✅</div>
            <h2 style="color: #2E7D32; margin-top: 0;">پرداخت با موفقیت انجام شد!</h2>
            <p style="font-size: 16px; line-height: 1.6;">تراکنش شما تایید گردید. لطفا برای مشاهده وضعیت سفارش به ربات تلگرام برگردید.</p>
            <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; border: 1px dashed #2e7d32; display: inline-block; margin-top: 20px;">
                <span style="font-size: 14px; color: #555;">کد پیگیری تراکنش (بانک):</span><br>
                <strong style="font-size: 18px; color: #2e7d32; font-family: monospace;">{ref_id}</strong>
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=success_html, content_type='text/html')


async def main():
    logger.info("Initializing Advanced Telegram Store Bot...")

    # Initialize Database Manager (aiosqlite)
    db = DatabaseManager(DB_PATH)
    await db.connect()
    await db.create_tables()

    # Initialize Bot with default HTML parse mode using DefaultBotProperties
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    # Initialize Dispatcher
    dp = Dispatcher()

    # Register Middlewares (Register on message and callback_query routers directly)
    dp.message.outer_middleware(DbMiddleware(db))
    dp.callback_query.outer_middleware(DbMiddleware(db))

    dp.message.outer_middleware(ThrottlingMiddleware())
    dp.callback_query.outer_middleware(ThrottlingMiddleware())

    dp.message.outer_middleware(ForceJoinMiddleware())
    dp.callback_query.outer_middleware(ForceJoinMiddleware())

    # Register Routers (Include wallet and referral routers cleanly)
    dp.include_router(base_router)
    dp.include_router(store_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    dp.include_router(wallet_router)
    dp.include_router(referral_router)
    dp.include_router(support_router)

    # Initialize Zarinpal Callback HTTP Server
    app = web.Application()
    app.router.add_get('/zarinpal/callback', handle_zarinpal_callback)
    app['bot'] = bot
    app['db'] = db

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEB_PORT)
    await site.start()
    logger.info(f"Zarinpal callback web server started on port {WEB_PORT}")

    # Initialize Phase 5 Automated Background Cloud Backup Scheduler
    # Starts as a lightweight, concurrent background task loop
    backup_task = asyncio.create_task(run_backup_scheduler(bot, db))

    try:
        # Graceful startup logging
        logger.info("Bot successfully loaded. Commencing polling...")
        # Start polling (Uncommented to ensure production runs correctly)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Critical error during polling execution: {e}")
    finally:
        # Cancel background tasks gracefully on exit
        backup_task.cancel()
        await runner.cleanup()

        # Graceful cleanup of resources on stop/interruption
        await bot.session.close()
        await db.close()
        logger.info("Bot and Database instances cleanly shut down.")

if __name__ == "__main__":
    # If file ran directly, run the main function asynchronously
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution terminated.")
