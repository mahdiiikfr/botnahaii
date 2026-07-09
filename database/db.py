import os
import secrets
import string
import logging
import aiosqlite

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Asynchronous SQLite Database Manager using aiosqlite.
    Manages connections, enforces table creations with foreign keys enabled,
    and exposes clean, asynchronous CRUD operations for our Telegram Store Bot.
    Supports usage as an async context manager or setup/teardown methods.
    """

    def __init__(self, db_path: str = "database/store.db"):
        self.db_path = db_path
        self._conn = None

    async def connect(self) -> aiosqlite.Connection:
        """
        Establishes connection to the SQLite database.
        Enables Foreign Key support and configures row factory to return Row objects.
        """
        if self._conn is not None:
            return self._conn

        # Ensure target directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = await aiosqlite.connect(self.db_path)
        # Enable ROW factory so we can access columns by name (dictionary-like)
        self._conn.row_factory = aiosqlite.Row

        # Enforce SQLite foreign keys
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.commit()

        logger.info(f"Connected to SQLite database at {self.db_path} with Foreign Keys enabled.")
        return self._conn

    async def close(self):
        """
        Closes the active database connection.
        """
        if self._conn is not None:
            await self._conn.close()
            logger.info("Database connection closed.")
            self._conn = None

    # Context Manager Protocol support
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def create_tables(self):
        """
        Creates all required SQLite database tables (users, categories, products, orders)
        if they do not exist already, with strict constraints.

        In Phase 5, the 'orders' schema is updated to support nullable 'product_id' (to handle
        wallet deposits) and a new 'amount' column to record payment sums.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() or use context manager.")

        queries = [
            # Categories Table
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            """,
            # Users Table
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                wallet_balance INTEGER NOT NULL DEFAULT 0,
                referral_code TEXT UNIQUE NOT NULL,
                invited_by INTEGER,
                join_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invited_by) REFERENCES users(user_id) ON DELETE SET NULL
            );
            """,
            # Products Table
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL,
                digital_data TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            );
            """,
            # Orders Table (Phase 5: product_id is nullable, amount column added)
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER,
                amount INTEGER,
                status TEXT NOT NULL CHECK(status IN ('pending', 'paid', 'delivered', 'rejected')),
                payment_receipt TEXT,
                date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );
            """
        ]

        async with self._conn.cursor() as cursor:
            for query in queries:
                await cursor.execute(query)
            await self._conn.commit()

        logger.info("Database tables initialized successfully (Phase 5 schema updated).")
        await self.seed_database()

    async def seed_database(self):
        """
        Seeds the database with standard categories and products as requested by the user,
        using INSERT OR IGNORE and duplicate existence checks to prevent duplicates.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        # Define categories to insert
        categories = [
            "اکانت پرمیوم 🌟",
            "گیفت کارت 🎁",
            "V P N (ترافیک نامحدود) 🛡️",
            "خدمات پنل فیلترشکن ⚙️",
            "V P S (سرورهای مجازی) 💻",
            "خدمات وب و برنامه‌نویسی 🌐"
        ]

        async with self._conn.cursor() as cursor:
            for cat in categories:
                await cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?);", (cat,))
            await self._conn.commit()

            # Retrieve category IDs
            cat_map = {}
            for cat in categories:
                await cursor.execute("SELECT id FROM categories WHERE name = ?;", (cat,))
                row = await cursor.fetchone()
                if row:
                    cat_map[cat] = row["id"]

            # Define products to insert
            products = [
                # Category: V P N (ترافیک نامحدود) 🛡️
                ("V P N (ترافیک نامحدود) 🛡️", "👤 تک کاربره", "اشتراک فیلترشکن تک کاربره با ترافیک نامحدود", 150000, 99, "VPN-1USER"),
                ("V P N (ترافیک نامحدود) 🛡️", "👥 دو کاربره", "اشتراک فیلترشکن دو کاربره با ترافیک نامحدود", 250000, 99, "VPN-2USER"),
                ("V P N (ترافیک نامحدود) 🛡️", "👥 سه کاربره", "اشتراک فیلترشکن سه کاربره با ترافیک نامحدود", 350000, 99, "VPN-3USER"),

                # Category: خدمات پنل فیلترشکن ⚙️
                ("خدمات پنل فیلترشکن ⚙️", "🌐 ثبت دامنه ir (فوری)", "ثبت فوری دامنه ملی دات آی آر برای اتصال به پنل فیلترشکن", 400000, 99, "DOMAIN-IR"),
                ("خدمات پنل فیلترشکن ⚙️", "💻 نصب و راه اندازی پنل سنایی پاسارگاد مرزبان", "نصب حرفه‌ای پنل‌های سنایی، پاسارگاد، مرزبان و کانفیگ‌های مربوطه", 500000, 99, "PANEL-INSTALL"),

                # Category: اکانت پرمیوم 🌟
                ("اکانت پرمیوم 🌟", "⏳ Gemini اکانت پرمیوم ۱۸ ماهه", "اکانت پرمیوم هوش مصنوعی گوگل Gemini به مدت ۱۸ ماه", 750000, 99, "GEMINI-18MO"),
                ("اکانت پرمیوم 🌟", "⏳ ChatGPT اکانت پرمیوم ۱ ماهه", "اشتراک ۱ ماهه اختصاصی ChatGPT Plus با دسترسی به GPT-4", 1000000, 99, "CHATGPT-1MO"),

                # Category: V P S (سرورهای مجازی) 💻
                ("V P S (سرورهای مجازی) 💻", "سرور ایران افرانت", "سرور مجازی ایران دیتاسنتر افرانت با پورت پرسرعت و آپتایم بالا", 1000000, 99, "VPS-IRAN"),
                ("V P S (سرورهای مجازی) 💻", "سرور خارج", "سرور مجازی خارج از کشور با پهنای باند گیگابیتی و آی‌پی ثابت", 800000, 99, "VPS-KHARIJ"),

                # Category: خدمات وب و برنامه‌نویسی 🌐
                ("خدمات وب و برنامه‌نویسی 🌐", "🌐 ثبت دامنه ir (فوری)", "ثبت دامنه ملی دات آی آر با مالکیت ۱۰۰٪ و فعالسازی سریع", 400000, 99, "WEB-DOMAIN-IR"),
                ("خدمات وب و برنامه‌نویسی 🌐", "🤖 ساخت ربات تلگرام", "طراحی و برنامه‌نویسی انواع ربات‌های تلگرامی پیشرفته و دلخواه", 1000000, 99, "TELEGRAM-BOT"),
                ("خدمات وب و برنامه‌نویسی 🌐", "💻 طراحی سایت", "طراحی و توسعه وب‌سایت‌های شخصی، شرکتی و فروشگاهی به صورت کاملاً اختصاصی (توافقی)", 0, 99, "WEBSITE-DESIGN")
            ]

            for cat_name, prod_name, desc, price, stock, digital_data in products:
                cat_id = cat_map.get(cat_name)
                if cat_id is not None:
                    # Check if product already exists under this category to prevent duplicate products
                    await cursor.execute(
                        "SELECT id FROM products WHERE category_id = ? AND name = ?;",
                        (cat_id, prod_name)
                    )
                    if not await cursor.fetchone():
                        await cursor.execute(
                            """
                            INSERT INTO products (category_id, name, description, price, stock, digital_data, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, 1);
                            """,
                            (cat_id, prod_name, desc, price, stock, digital_data)
                        )
            await self._conn.commit()
        logger.info("Database seeded with requested categories and products successfully.")

    # --- Utility Methods ---
    def _generate_referral_code(self, length: int = 8) -> str:
        """
        Generates a secure, random alphanumeric string for user referrals.
        """
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    # --- CRUD Operations ---

    async def add_user(self, user_id: int, username: str = None, invited_by: int = None) -> bool:
        """
        Inserts a new user into the database. If the user already exists (INSERT OR IGNORE),
        it ignores insertion and keeps existing data intact.
        Generates a unique 8-character referral code for each user.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        referral_code = self._generate_referral_code()

        async with self._conn.cursor() as cursor:
            # Check if referral_code is already used just in case (collision avoidance)
            while True:
                await cursor.execute("SELECT 1 FROM users WHERE referral_code = ?", (referral_code,))
                if not await cursor.fetchone():
                    break
                referral_code = self._generate_referral_code()

            # Perform standard INSERT OR IGNORE
            await cursor.execute(
                """
                INSERT OR IGNORE INTO users (user_id, username, wallet_balance, referral_code, invited_by)
                VALUES (?, ?, 0, ?, ?);
                """,
                (user_id, username, referral_code, invited_by)
            )
            await self._conn.commit()
            return cursor.rowcount > 0

    async def get_user(self, user_id: int) -> aiosqlite.Row:
        """
        Retrieves user information by user_id.
        Returns an aiosqlite.Row object allowing column dictionary access (or None if not found).
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT user_id, username, wallet_balance, referral_code, invited_by, join_date FROM users WHERE user_id = ?;",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def get_categories(self) -> list[aiosqlite.Row]:
        """
        Retrieves all categories from the categories table.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute("SELECT id, name FROM categories ORDER BY name ASC;") as cursor:
            return await cursor.fetchall()

    async def get_active_products(self, category_id: int) -> list[aiosqlite.Row]:
        """
        Retrieves all active products belonging to a given category (is_active = 1).
        Returns products even if they are out of stock (stock = 0).
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT id, category_id, name, description, price, stock, digital_data, is_active FROM products WHERE category_id = ? AND is_active = 1 ORDER BY id ASC;",
            (category_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def create_order(
        self,
        user_id: int,
        product_id: int | None,
        status: str = 'pending',
        payment_receipt: str = None,
        amount: int | None = None
    ) -> int:
        """
        Creates an order inside the orders table and returns the autoincremented order ID.
        Status constraint must be one of: 'pending', 'paid', 'delivered', 'rejected'.
        Allows product_id to be None when registering a wallet deposit.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        if status not in ('pending', 'paid', 'delivered', 'rejected'):
            raise ValueError("Status must be one of: 'pending', 'paid', 'delivered', 'rejected'")

        async with self._conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO orders (user_id, product_id, amount, status, payment_receipt)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, product_id, amount, status, payment_receipt)
            )
            await self._conn.commit()
            return cursor.lastrowid

    # --- Phase 5 Custom Database Operations ---

    async def update_user_balance(self, user_id: int, amount_delta: int) -> bool:
        """
        Adds or subtracts balance to/from user's wallet.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?;",
                (amount_delta, user_id)
            )
            await self._conn.commit()
            return cursor.rowcount > 0

    async def get_user_by_referral_code(self, code: str) -> aiosqlite.Row | None:
        """
        Locates user data by custom unique referral_code string.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT user_id, username, wallet_balance, referral_code, invited_by, join_date FROM users WHERE referral_code = ?;",
            (code,)
        ) as cursor:
            return await cursor.fetchone()

    async def get_invited_users_count(self, user_id: int) -> int:
        """
        Counts the total number of sub-users invited by the specified user_id.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT COUNT(user_id) as count FROM users WHERE invited_by = ?;",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_user_orders_paginated(self, user_id: int, limit: int = 1, offset: int = 0) -> list[aiosqlite.Row]:
        """
        Retrieves user orders (both deposits and purchases) ordered by date descending, with pagination.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            """
            SELECT o.id, o.product_id, o.amount, o.status, o.payment_receipt, o.date, p.name as product_name, p.digital_data
            FROM orders o
            LEFT JOIN products p ON o.product_id = p.id
            WHERE o.user_id = ?
            ORDER BY o.date DESC, o.id DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, limit, offset)
        ) as cursor:
            return await cursor.fetchall()

    async def get_total_user_orders_all_count(self, user_id: int) -> int:
        """
        Counts ALL user's orders (both deposits and product purchases).
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT COUNT(id) as count FROM orders WHERE user_id = ?;",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_total_user_count(self) -> int:
        """
        Counts the total registered users in the system. Used for backup metadata.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute("SELECT COUNT(user_id) as count FROM users;") as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_total_user_orders_count(self, user_id: int) -> int:
        """
        Counts total orders completed or pending for a specific user.
        Excludes wallet deposit order types where product_id is None.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected.")

        async with self._conn.execute(
            "SELECT COUNT(id) as count FROM orders WHERE user_id = ? AND product_id IS NOT NULL;",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0
