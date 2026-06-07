"""
Main bot entry point with HTTP health check for Railway.
"""

import asyncio
import logging
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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


class HealthHandler(BaseHTTPRequestHandler):
    """معالج صحي بسيط لـ Railway"""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass


def run_health_server():
    """تشغيل خادم HTTP للفحص الصحي"""
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"✅ Health server on port {port}")
    server.serve_forever()


async def periodic_cleanup():
    """تنظيف دوري للـ rate limiter"""
    while True:
        try:
            await asyncio.sleep(300)
            rate_limiter.clean_old(max_age=600)
        except asyncio.CancelledError:
            break


async def main():
    logger.info("🚀 Starting bot...")
    
    # تشغيل خادم HTTP في Thread منفصل
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # قاعدة البيانات
    db = Database()
    try:
        await db.connect()
    except Exception as e:
        logger.critical(f"Database error: {e}")
        return
    
    # التحميل
    dl = Downloader()
    set_shared_objects(db, dl)
    
    # التطبيق
    app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(app)
    
    # مهمة التنظيف
    asyncio.create_task(periodic_cleanup())
    
    logger.info("✅ Bot is running...")
    
    # بدء الاستقبال
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
