import os
from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "database/store.db")

# Force Join Channel Configuration
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@YourChannel")

# Throttling Configuration
try:
    THROTTLING_RATE_LIMIT = float(os.getenv("THROTTLING_RATE_LIMIT", "1.5"))
except ValueError:
    THROTTLING_RATE_LIMIT = 1.5

# Admin and Card details Configuration (Phase 4)
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
except ValueError:
    ADMIN_ID = 123456789

CARD_NUMBER = os.getenv("CARD_NUMBER", "6037-9911-2233-4455")
CARD_HOLDER = os.getenv("CARD_HOLDER", "امیر رضایی")
