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
    # Use an in-memory/temporary DB or a local file for the test
    test_db_path = "database/test_store.db"

    # Ensure any previous test db file is removed before starting
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    logger.info(f"Starting test suite using database: {test_db_path}")

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
        # INSERT OR IGNORE won't throw error but rowcount will be 0, returning False or True depending on implementation.
        # Let's fetch and verify username didn't get modified (ignored) and referral code didn't change
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
            await cursor.execute("INSERT INTO categories (name) VALUES (?), (?);", ("Digital Keys", "Gift Cards"))
            await db._conn.commit()

        categories = await db.get_categories()
        assert len(categories) == 2, f"Expected 2 categories, found {len(categories)}"
        assert categories[0]["name"] == "Digital Keys", "Categories alphabet order mismatch!"
        logger.info(f"[PASS] Retrieved all categories: {[dict(c) for c in categories]}")

        category_id = categories[0]["id"]

        # Test 6: Products Creation and Active Products fetch
        async with db._conn.cursor() as cursor:
            # Active product
            await cursor.execute(
                """
                INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (category_id, "Telegram Premium 1 Year", "1 Year Subscription Key", 1500, 10, "TG-PREM-1YR-KEY-XYZ", 1)
            )
            # Inactive product
            await cursor.execute(
                """
                INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (category_id, "Deprecated Subscription", "Expired key", 500, 0, "EXPIRED-KEY", 0)
            )
            await db._conn.commit()

        active_products = await db.get_active_products(category_id)
        assert len(active_products) == 1, f"Expected 1 active product, found {len(active_products)}"
        assert active_products[0]["name"] == "Telegram Premium 1 Year", "Product name mismatch"
        logger.info(f"[PASS] Retrieved active products for category {category_id}: {[dict(p) for p in active_products]}")

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

    # Cleanup test db file
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        logger.info(f"Cleaned up temporary test database at {test_db_path}.")

    logger.info("====================================")
    logger.info("ALL TESTS COMPLETED SUCCESSFULLY!")
    logger.info("====================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
