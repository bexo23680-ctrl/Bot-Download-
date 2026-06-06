"""
Main bot entry point.
"""

import asyncio
import logging
import os
from pathlib import Path

from telegram.ext import Application

from config import BOT_TOKEN, LOG_LEVEL, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW
from database import Database
from downloader import Downloader
from handlers import set_shared_objects, register_handlers
from anti_spam import rate_limiter

# Logging setup
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def periodic_cleanup():
    """Periodically clean rate limiter memory."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        rate_limiter.clean_old(max_age=600)

async def main():
    # Initialize database
    db = Database()
    await db.connect()

    # Initialize downloader
    dl = Downloader()

    # Share objects with handlers
    set_shared_objects(db, dl)

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(app)

    # Start periodic cleanup task
    asyncio.create_task(periodic_cleanup())

    logger.info("Bot started")
    try:
        await app.run_polling()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
