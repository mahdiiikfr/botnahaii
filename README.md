# Telegram Advanced Store Bot - Phase 1

This repository contains the foundational project architecture, environment setup, and the SQLite Database Layer for a highly advanced Single-Page Application (SPA) style Telegram Store Bot.

Phase 1 focus lies entirely on establishing a modular, clean, and extensible directory structure, and defining the database schemas using `aiosqlite` with comprehensive validation, security constraints, and robust async CRUD operations.

---

## 1. Project Directory Tree

Below is the established project tree structure. Inside each directory, modular templates/boilerplates and `__init__.py` files are set up, ensuring seamless transition to future phases (handlers, keyboards, middlewares, and utilities):

```text
.
├── .env                  # Environmental variables (secrets, DB configuration)
├── .env.example          # Sample template for environmental variables
├── config.py             # Configuration loader using python-dotenv
├── main.py               # Main bot entry point (aiogram 3.x setup boilerplate)
├── requirements.txt      # Project dependencies (aiogram, aiosqlite, dotenv)
├── database/
│   ├── __init__.py
│   ├── db.py             # Robust, async DatabaseManager (aiosqlite)
│   └── test_db.py        # Complete automated database testing script
├── handlers/
│   └── __init__.py       # Placeholder for future bot handlers
├── keyboards/
│   └── __init__.py       # Placeholder for future keyboard definitions
├── middlewares/
│   └── __init__.py       # Placeholder for future middlewares
└── utils/
    └── __init__.py       # Placeholder for utility helper functions
```

---

## 2. SQLite Database Schema & Specifications

We have designed a highly-secure database schema with SQLite-enforced constraints. In `database/db.py`, SQLite's foreign keys constraint is explicitly enabled (`PRAGMA foreign_keys = ON;`) on startup, and `aiosqlite.Row` factory is configured so that query outputs are retrieved as dictionary-like objects.

### Tables Schema Definitions:

1. **`users`**:
   - `user_id` (`INTEGER PRIMARY KEY`): Safe for Telegram's 64-bit integer IDs.
   - `username` (`TEXT`): User's Telegram username.
   - `wallet_balance` (`INTEGER`): Stored in the smallest currency unit (e.g. cents) to prevent floating-point precision issues. Defaults to `0`.
   - `referral_code` (`TEXT UNIQUE NOT NULL`): Secure, random 8-character alphanumeric string generated during user insertion.
   - `invited_by` (`INTEGER`): References `users(user_id)` with `ON DELETE SET NULL`.
   - `join_date` (`TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`): ISO 8601 string representation.

2. **`categories`**:
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `name` (`TEXT UNIQUE NOT NULL`)

3. **`products`**:
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `category_id` (`INTEGER NOT NULL`): Foreign key referencing `categories(id)` with `ON DELETE CASCADE`.
   - `name` (`TEXT NOT NULL`)
   - `description` (`TEXT`)
   - `price` (`INTEGER NOT NULL`): Stored in cents.
   - `stock` (`INTEGER NOT NULL`)
   - `digital_data` (`TEXT NULL`): Optional text/file ID for auto-delivery (can support services/physical items as well).
   - `is_active` (`INTEGER NOT NULL DEFAULT 1`): Acts as Boolean.

4. **`orders`**:
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `user_id` (`INTEGER NOT NULL`): Foreign key referencing `users(user_id)` with `ON DELETE CASCADE`.
   - `product_id` (`INTEGER NOT NULL`): Foreign key referencing `products(id)` with `ON DELETE CASCADE`.
   - `status` (`TEXT NOT NULL`): Enforced with custom check constraint `CHECK(status IN ('pending', 'paid', 'delivered', 'rejected'))`.
   - `payment_receipt` (`TEXT NULL`)
   - `date` (`TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`): ISO 8601 string representation.

---

## 3. Asynchronous CRUD Operations

The `DatabaseManager` class in `database/db.py` contains the following asynchronous CRUD operations:

- `add_user(user_id, username, invited_by)`: Inserts a new user safely using `INSERT OR IGNORE` so that if a user restarts the bot, their wallet and existing referral codes are never overwritten. Generates a unique 8-character referral code with duplicate-collision protection.
- `get_user(user_id)`: Retrieves a specific user's Row record.
- `get_categories()`: Retrieves all categories sorted alphabetically by name.
- `get_active_products(category_id)`: Retrieves all active products (even if stock is 0, to handle Out of Stock UI later) under the given category ID.
- `create_order(user_id, product_id, status)`: Creates an order with strict check constraints and returns the autoincremented order ID.

---

## 4. How to Install and Run the Test Suite

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure `.env`**:
   A sample `.env` configuration is provided. Modify it to point to your desired database path or Telegram Bot Token if needed.

3. **Run Database Integration Tests**:
   We have built a comprehensive testing script `database/test_db.py` that verifies the initialization of tables, checks insert-or-ignore behavior, validates referral code constraints, and verifies foreign keys / check constraints.

   To run:
   ```bash
   python database/test_db.py
   ```
