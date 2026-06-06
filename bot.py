"""
Main bot entry point.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from telegram.ext import Application

from config import BOT_TOKEN, LOG_LEVEL
from database import Database
from downloader import Downloader
from handlers import set_shared_objects, register_handlers
from anti_spam import rate_limiter

# Create logs directory
os.makedirs("logs", exist_ok=True)

# Logging setup
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global references for cleanup
db = None
app = None
cleanup_task = None


async def periodic_cleanup():
    """Periodically clean rate limiter memory."""
    while True:
        try:
            await asyncio.sleep(300)  # every 5 minutes
            rate_limiter.clean_old(max_age=600)
            logger.debug("Rate limiter cleanup completed")
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")


async def shutdown(signal=None):
    """Cleanup and shutdown gracefully."""
    global db, app, cleanup_task
    
    logger.info(f"Shutting down... (signal: {signal})")
    
    # Cancel cleanup task
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    # Stop bot polling
    if app:
        try:
            if app.running:
                await app.stop()
                logger.info("Bot stopped")
        except Exception as e:
            logger.warning(f"Error stopping bot: {e}")
    
    # Close database
    if db:
        await db.close()
    
    logger.info("Shutdown complete")


async def main():
    """Main function to run the bot."""
    global db, app, cleanup_task
    
    logger.info("Starting bot initialization...")
    
    # Initialize database with error handling
    db = Database()
    try:
        await db.connect()
    except Exception as e:
        logger.critical(f"Failed to connect to database: {e}")
        logger.critical("Exiting - cannot operate without database")
        return

    # Initialize downloader
    dl = Downloader()
    logger.info(f"Download directory: {dl.download_dir}")

    # Share objects with handlers
    set_shared_objects(db, dl)

    # Build application
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        register_handlers(app)
        logger.info("Bot application built successfully")
    except Exception as e:
        logger.critical(f"Failed to build application: {e}")
        await db.close()
        return

    # Start periodic cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup())

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(shutdown(s))
            )
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    logger.info("=" * 50)
    logger.info("Bot is starting polling...")
    logger.info("=" * 50)

    try:
        # Start polling
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=["message", "callback_query"])
        
        # Keep running until stopped
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour intervals
            
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.critical(f"Critical error in main loop: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    try:
        # Run the main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
