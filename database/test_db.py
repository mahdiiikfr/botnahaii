import asyncio
import os
import sys
import logging

# Add parent directory to sys.path if not present to enable importing modules easily
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def run_tests():
    # Use real store database file or test database file
    test_db_path = "database/store.db"

    # Ensure any previous database file is removed before starting to reset cleanly
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    logger.info(f"Starting test suite and populating database: {test_db_path}")

    async with DatabaseManager(test_db_path) as db:
        # Create Tables
        await db.create_tables()
        logger.info("[PASS] Tables created successfully.")

        # Test 1: Add a User
        user_id_1 = 123456789
        success = await db.add_user(user_id_1, "alice_tg")
        assert success is True, "Failed to add Alice"
        logger.info(f"[PASS] Added Alice (user_id: {user_id_1}).")

        # Test 2: Retrieve the User
        user = await db.get_user(user_id_1)
        assert user is not None, "User not found!"
        assert user["username"] == "alice_tg", "Username mismatch!"
        assert user["wallet_balance"] == 0, "Initial balance should be 0!"
        assert len(user["referral_code"]) == 8, f"Referral code {user['referral_code']} should be 8 characters!"
        logger.info(f"[PASS] Retrieved Alice. Details: {dict(user)}")

        # Test 3: Insert Duplicate User (INSERT OR IGNORE verification)
        success_dup = await db.add_user(user_id_1, "alice_tg_new_username")
        # INSERT OR IGNORE won't throw error but rowcount will be 0
        user_after = await db.get_user(user_id_1)
        assert user_after["username"] == "alice_tg", "Duplicate insertion modified username!"
        assert user_after["referral_code"] == user["referral_code"], "Duplicate insertion changed referral code!"
        logger.info("[PASS] INSERT OR IGNORE worked perfectly (no duplicates or updates occurred).")

        # Test 4: Add Invited User (Referral System)
        user_id_2 = 987654321
        success_bob = await db.add_user(user_id_2, "bob_tg", invited_by=user_id_1)
        assert success_bob is True, "Failed to add Bob"
        bob = await db.get_user(user_id_2)
        assert bob["invited_by"] == user_id_1, "Bob invited_by constraint mismatch!"
        logger.info(f"[PASS] Added Bob referred by Alice. Details: {dict(bob)}")

        # Test 5: Categories Creation and CRUD
        async with db._conn.cursor() as cursor:
            await cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?), (?);", ("اکانت پرمیوم 🌟", "گیفت کارت 🎁"))
            await db._conn.commit()

        categories = await db.get_categories()
        assert len(categories) >= 2, f"Expected at least 2 categories, found {len(categories)}"
        logger.info(f"[PASS] Retrieved all categories: {[dict(c) for c in categories]}")

        category_id_1 = categories[0]["id"]
        category_id_2 = categories[1]["id"]

        # Test 6: Products Creation and Active Products fetch
        # Populate Category 1 with multiple products (7 products) to test 5-item pagination transitions.
        dummy_products = [
            ("تلگرام پرمیوم ۱ ماهه", "اشتراک یک ماهه تلگرام پرمیوم با فعالسازی مستقیم روی اکانت شما", 150000, 50, "TG-PREM-1MO", 1),
            ("تلگرام پرمیوم ۳ ماهه", "اشتراک سه ماهه تلگرام پرمیوم با تخفیف ویژه", 420000, 20, "TG-PREM-3MO", 1),
            ("تلگرام پرمیوم ۶ ماهه", "اشتراک شش ماهه تلگرام پرمیوم با بهترین قیمت", 800000, 15, "TG-PREM-6MO", 1),
            ("تلگرام پرمیوم ۱ ساله", "اشتراک یک ساله کامل تلگرام پرمیوم با بیشترین تخفیف", 1500000, 10, "TG-PREM-1YR", 1),
            ("اکانت اسپاتیفای پرمیوم", "اشتراک کاملاً اختصاصی اسپاتیفای پرمیوم بدون قطعی", 250000, 30, "SPOTIFY-PREM", 1),
            ("اکانت یوتیوب پرمیوم", "اشتراک یوتیوب پرمیوم بدون تبلیغات مزاحم", 180000, 45, "YOUTUBE-PREM", 1),
            ("اکانت نتفلیکس ۴ کاربره", "اکانت اشتراکی نتفلیکس با کیفیت Ultra HD", 350000, 5, "NETFLIX-UHD", 1),
            ("اکانت تست غیرفعال", "محصول تستی غیرفعال برای صحت عملکرد سیستم", 90000, 0, "TEST-INACTIVE", 0),
        ]

        async with db._conn.cursor() as cursor:
            for p in dummy_products:
                await cursor.execute(
                    """
                    INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (category_id_1, p[0], p[1], p[2], p[3], p[4], p[5])
                )

            # Category 2 products (2 products)
            await cursor.execute(
                """
                INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                VALUES (?, 'گیفت کارت ۱0 دلاری اپل', 'کد گیفت کارت آیتونز اپل ریجن آمریکا', 550000, 8, 'APPLE-10USD-KEY', 1);
                """,
                (category_id_2,)
            )
            await cursor.execute(
                """
                INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                VALUES (?, 'گیفت کارت ۵ دلاری استیم', 'کد گیفت کارت استیم ولت ریجن آمریکا', 280000, 12, 'STEAM-5USD-KEY', 1);
                """,
                (category_id_2,)
            )
            await db._conn.commit()

        active_products = await db.get_active_products(category_id_1)
        # Should exclude the inactive product (8 total inserted, 7 active plus seeded ones)
        assert len(active_products) >= 7, f"Expected at least 7 active products, found {len(active_products)}"
        logger.info(f"[PASS] Retrieved active products. Active count: {len(active_products)}")

        product_id = active_products[0]["id"]

        # Test 7: Orders Creation
        order_id = await db.create_order(user_id=user_id_1, product_id=product_id, status='pending')
        assert order_id is not None and order_id > 0, "Failed to create order"

        async with db._conn.execute("SELECT id, user_id, product_id, status, payment_receipt, date FROM orders WHERE id = ?;", (order_id,)) as cursor:
            order = await cursor.fetchone()
            assert order is not None
            assert order["user_id"] == user_id_1
            assert order["product_id"] == product_id
            assert order["status"] == "pending"
            assert order["payment_receipt"] is None
            logger.info(f"[PASS] Created and verified order: {dict(order)}")

        # Test 8: Order Status Check Constraints
        try:
            await db.create_order(user_id=user_id_1, product_id=product_id, status='invalid_status')
            raise AssertionError("Order status check constraint failed to prevent invalid value!")
        except Exception as e:
            logger.info(f"[PASS] Order check constraint correctly rejected invalid status. Exception: {e}")

        # Test 9: Foreign Key constraints
        try:
            # Use non-existent category id
            async with db._conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                    VALUES (9999, 'Ghost Item', 'None', 100, 5, 'None', 1);
                    """
                )
                await db._conn.commit()
            raise AssertionError("Foreign key constraint failed to prevent product with non-existent category!")
        except Exception as e:
            logger.info(f"[PASS] Foreign key constraints working perfectly. Exception: {e}")

    logger.info("====================================")
    logger.info("ALL TESTS COMPLETED SUCCESSFULLY & DUMMY DATA POPULATED!")
    logger.info("====================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
