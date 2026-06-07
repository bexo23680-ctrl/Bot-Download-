"""
Main bot entry point.
"""

import asyncio
import logging
import os
import sys

from telegram.ext import Application

from config import BOT_TOKEN, LOG_LEVEL
from database import Database
from downloader import Downloader
from handlers import set_shared_objects, register_handlers
from anti_spam import rate_limiter

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def periodic_cleanup():
    """Periodically clean rate limiter memory."""
    while True:
        try:
            await asyncio.sleep(300)
            rate_limiter.clean_old(max_age=600)
        except asyncio.CancelledError:
            break


async def main():
    logger.info("Starting bot...")
    
    # Database
    db = Database()
    try:
        await db.connect()
    except Exception as e:
        logger.critical(f"Database error: {e}")
        return
    
    # Downloader
    dl = Downloader()
    set_shared_objects(db, dl)
    
    # Application
    app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(app)
    
    # Cleanup task
    asyncio.create_task(periodic_cleanup())
    
    logger.info("Bot is running...")
    
    # Start polling
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
