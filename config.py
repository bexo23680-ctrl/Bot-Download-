"""
Environment & configuration loader.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

ADMINS = list(map(int, os.getenv("ADMINS", "").split(","))) if os.getenv("ADMINS") else []

DATABASE_PATH = os.getenv("DATABASE_PATH", "database.db")
COOKIES_FILE = os.getenv("COOKIES_FILE", None)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DAILY_LIMIT_NON_PREMIUM = int(os.getenv("DAILY_LIMIT_NON_PREMIUM", "5"))
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))          # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))   # seconds
