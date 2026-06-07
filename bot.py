"""
Main bot entry point.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

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
            await asyncio.sleep(300)
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
    
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    if app:
        try:
            if app.running:
                await app.stop()
                logger.info("Bot stopped")
        except Exception as e:
            logger.warning(f"Error stopping bot: {e}")
    
    if db:
        await db.close()
    
    logger.info("Shutdown complete")


async def delete_webhook():
    """Delete any existing webhook before starting polling."""
    temp_app = Application.builder().token(BOT_TOKEN).build()
    await temp_app.initialize()
    await temp_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted (if existed)")
    await temp_app.shutdown()


async def main():
    """Main function to run the bot."""
    global db, app, cleanup_task
    
    logger.info("=" * 50)
    logger.info("Starting bot initialization...")
    logger.info("=" * 50)
    
    # Delete webhook first
    try:
        await delete_webhook()
    except Exception as e:
        logger.warning(f"Failed to delete webhook: {e}")
    
    # Initialize database with error handling
    db = Database()
    try:
        await db.connect()
        logger.info("Database connected successfully")
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
        
        # ✅ تسجيل جميع المعالجات
        register_handlers(app)
        
        logger.info("Bot application built successfully")
        logger.info(f"Registered handlers: {len(app.handlers)} groups")
        
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
            logger.warning(f"Signal handler not supported for {sig}")

    logger.info("=" * 50)
    logger.info("Bot is starting polling...")
    logger.info("=" * 50)

    try:
        await app.initialize()
        await app.start()
        
        # ✅ تشغيل polling مع جميع أنواع التحديثات
        await app.updater.start_polling(
            allowed_updates=["message", "callback_query", "edited_message"],
            drop_pending_updates=True,  # تجاهل الرسائل القديمة
        )
        
        logger.info("✅ Polling started successfully!")
        logger.info("✅ Bot is now running and ready to receive commands!")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
            
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.critical(f"Critical error in main loop: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
