"""
Telegram bot handlers.
"""

import asyncio
import logging
import os
from typing import Optional
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode

from config import MAINTENANCE_MODE, ADMINS, DAILY_LIMIT_NON_PREMIUM, RATE_LIMIT_WINDOW
from database import Database
from downloader import Downloader
from anti_spam import rate_limiter
from utils import is_valid_instagram_url
from subscription import check_user_subscription, send_subscription_message, get_subscription_keyboard

logger = logging.getLogger(__name__)

db: Optional[Database] = None
downloader: Optional[Downloader] = None

# Store active download tasks
active_downloads: dict = {}

def set_shared_objects(database: Database, dl: Downloader):
    global db, downloader
    db = database
    downloader = dl

# -------------------------------
# Helper: maintenance check
# -------------------------------
async def is_maintenance(user_id: int) -> bool:
    if MAINTENANCE_MODE and user_id not in ADMINS:
        return True
    return False

# -------------------------------
# Command handlers
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية مع فحص الاشتراك."""
    user = update.effective_user
    user_id = user.id
    
    # Add user to database
    await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
    
    # فحص الاشتراك أولاً
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    
    # المستخدم مشترك - ترحيب عادي
    await update.message.reply_text(
        "👋 *Welcome to Instagram Media Downloader!*\n\n"
        "Send me a public Instagram URL (Reels, Videos, Photos, Carousels) and I'll download it in the highest quality.\n\n"
        "Commands:\n/start – Start\n/help – Help\n/stats – Your usage statistics\n/settings – Subscription info",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر المساعدة مع فحص الاشتراك."""
    user_id = update.effective_user.id
    
    # فحص الاشتراك
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    
    await update.message.reply_text(
        "📘 *How to use:*\n"
        "1. Copy a public Instagram link (post, reel, video).\n"
        "2. Send the link to this bot.\n"
        "3. Wait while I download and send the file(s).\n\n"
        "⚠️ The account must be *public*.\n"
        "💎 Premium users get unlimited daily downloads; free users limited to "
        f"{DAILY_LIMIT_NON_PREMIUM} downloads/day.\n\n"
        "For issues, contact an admin.",
        parse_mode=ParseMode.MARKDOWN
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المستخدم."""
    user = update.effective_user
    user_id = user.id
    
    # فحص الاشتراك
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    
    user_data = await db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("No data yet. Send a link first!")
        return
    
    total = user_data['total_downloads']
    premium = "✅" if user_data['is_premium'] else "❌"
    daily = await db.get_daily_count(user_id)
    limit = "∞" if user_data['is_premium'] else str(DAILY_LIMIT_NON_PREMIUM)
    
    await update.message.reply_text(
        f"📊 *Your Stats*\n"
        f"• Total downloads: {total}\n"
        f"• Today: {daily}/{limit}\n"
        f"• Premium: {premium}\n\n"
        f"Use /settings to manage subscription.",
        parse_mode=ParseMode.MARKDOWN
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إعدادات المستخدم."""
    user = update.effective_user
    user_id = user.id
    
    # فحص الاشتراك
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    
    user_data = await db.get_user(user_id)
    premium = user_data['is_premium'] if user_data else False
    
    text = (
        "⚙️ *Settings*\n"
        f"Premium: {'Yes' if premium else 'No'}\n"
        "To upgrade, contact the admin.\n"
    )
    if not premium:
        text += f"Daily limit: {DAILY_LIMIT_NON_PREMIUM} downloads."
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# -------------------------------
# Callback handlers
# -------------------------------
async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الضغط على زر التحقق من الاشتراك."""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # التحقق من الاشتراك مرة أخرى
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    
    if is_subscribed:
        await query.message.delete()
        
        # إرسال رسالة ترحيب
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 *تم التحقق بنجاح!*\n\n"
                "يمكنك الآن استخدام البوت.\n"
                "أرسل رابط Instagram للتحميل.\n\n"
                "للمساعدة: /help"
            ),
            parse_mode="Markdown"
        )
    else:
        # تحديث الرسالة مع القنوات المتبقية
        channels_list = "\n".join([
            f"• [{ch['name']}]({ch['url']})"
            for ch in unsubscribed
        ])
        
        new_text = (
            "⚠️ *لم تشترك بعد في:*\n\n"
            f"{channels_list}\n\n"
            "اشترك ثم اضغط على الزر أدناه 👇"
        )
        
        keyboard = get_subscription_keyboard(unsubscribed)
        
        try:
            await query.message.edit_text(
                new_text,
                reply_markup=keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error updating subscription message: {e}")

# -------------------------------
# Message handler (Instagram URL)
# -------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الرئيسي مع فحص الاشتراك الإجباري."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    # ============ فحص الاشتراك الإجباري ============
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    # =============================================

    # Maintenance check
    if await is_maintenance(user_id):
        await update.message.reply_text("🛠️ Bot is under maintenance. Please try again later.")
        return

    # Validate URL
    if not is_valid_instagram_url(text):
        await update.message.reply_text("❌ Please send a valid Instagram URL.")
        return

    # Rate limiting
    if not rate_limiter.is_allowed(user_id):
        wait = RATE_LIMIT_WINDOW
        await update.message.reply_text(f"⏳ Too many requests. Please wait {wait} seconds.")
        return

    # User DB update
    await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")

    # Ban check
    if await db.is_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    # Subscription / daily limit
    is_prem = await db.is_premium(user_id)
    if not is_prem:
        daily = await db.get_daily_count(user_id)
        if daily >= DAILY_LIMIT_NON_PREMIUM:
            await update.message.reply_text(
                "⛔ Daily limit reached. Upgrade to premium for unlimited downloads.\n"
                "Contact an admin or use /settings."
            )
            return

    # Start download process
    status_msg = await update.message.reply_text("⏳ Analysing link...")

    if user_id in active_downloads:
        await status_msg.edit_text("Another download is already in progress. Please wait.")
        return

    active_downloads[user_id] = True

    try:
        # 1. Get media info
        info = await downloader.get_media_info(text)
        media_type = info.get('type', 'unknown')
        title = info.get('title', 'Instagram media')

        # 2. Prepare progress callback
        async def progress(percent: float, speed: str):
            try:
                await status_msg.edit_text(f"📥 Downloading... {percent:.1f}%\n⚡ {speed}")
            except Exception:
                pass

        # 3. Download media
        files = await downloader.download(text, progress)

        # 4. Send files one by one
        await status_msg.edit_text("📤 Uploading to Telegram...")

        sent_count = 0
        for idx, filepath in enumerate(files):
            if not os.path.exists(filepath):
                logger.warning(f"File not found, skipping: {filepath}")
                continue
            
            file_size = os.path.getsize(filepath)
            if file_size > 50 * 1024 * 1024:
                await status_msg.reply_text(
                    f"⚠️ File too large ({file_size / 1024 / 1024:.1f}MB). Telegram limit is 50MB."
                )
                continue
            
            caption = title if idx == 0 else None
            try:
                with open(filepath, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=os.path.basename(filepath),
                        caption=caption,
                        read_timeout=120,
                        write_timeout=120,
                    )
                sent_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to send file {filepath}: {e}")
                await status_msg.reply_text(f"⚠️ Failed to send one file: {os.path.basename(filepath)}")

        if sent_count == 0:
            await status_msg.edit_text("❌ Failed to send any files. Please try again.")
        else:
            await db.increment_downloads(user_id)
            await status_msg.edit_text(f"✅ Download complete! ({sent_count} file(s) sent)")
    
    except Exception as e:
        logger.error(f"Error processing {text}: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        active_downloads.pop(user_id, None)
        if 'files' in locals() and files:
            parent_dir = Path(files[0]).parent if files else None
            if parent_dir and os.path.exists(parent_dir):
                try:
                    import shutil
                    shutil.rmtree(parent_dir)
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")

# -------------------------------
# Admin commands
# -------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم الأدمن."""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Admin only.")
        return

    total_users, premium_users, total_downloads = await db.get_stats()
    await update.message.reply_text(
        f"👑 *Admin Panel*\n\n"
        f"👥 Total users: {total_users}\n"
        f"💎 Premium: {premium_users}\n"
        f"📥 Total downloads: {total_downloads}\n\n"
        f"Commands:\n"
        f"/broadcast <msg> – Send message to all users\n"
        f"/ban <user_id> – Ban a user\n"
        f"/unban <user_id> – Unban a user\n"
        f"/premium <user_id> – Grant premium\n"
        f"/unpremium <user_id> – Remove premium\n"
        f"/maintenance on/off – Toggle maintenance mode\n"
        f"/channels – Show required channels",
        parse_mode=ParseMode.MARKDOWN
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة لجميع المستخدمين."""
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    msg = ' '.join(context.args)
    async with db._conn.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
        users = await cursor.fetchall()
    
    count = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Broadcast to {uid} failed: {e}")
    
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر مستخدم."""
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    await db.set_ban(uid, True)
    await update.message.reply_text(f"🚫 User {uid} banned.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فك حظر مستخدم."""
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    await db.set_ban(uid, False)
    await update.message.reply_text(f"✅ User {uid} unbanned.")

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منح بريميوم."""
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /premium <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    await db.set_premium(uid, True)
    await update.message.reply_text(f"💎 User {uid} now premium.")

async def unpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة بريميوم."""
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /unpremium <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    await db.set_premium(uid, False)
    await update.message.reply_text(f"💔 User {uid} no longer premium.")

async def maintenance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل/إيقاف وضع الصيانة."""
    global MAINTENANCE_MODE
    if update.effective_user.id not in ADMINS:
        return
    if not context.args or context.args[0].lower() not in ('on', 'off'):
        await update.message.reply_text("Usage: /maintenance on|off")
        return
    new_state = context.args[0].lower() == 'on'
    MAINTENANCE_MODE = new_state
    await update.message.reply_text(f"🛠️ Maintenance mode {'enabled' if new_state else 'disabled'}.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القنوات الإجبارية الحالية."""
    if update.effective_user.id not in ADMINS:
        return
    
    from subscription import REQUIRED_CHANNELS
    
    text = "*📢 القنوات الإجبارية:*\n\n"
    for i, ch in enumerate(REQUIRED_CHANNELS, 1):
        text += f"{i}. {ch['name']} - {ch['username']}\n"
    
    text += "\nلتعديل القنوات، عدل ملف `subscription.py`"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# -------------------------------
# Handler registration
# -------------------------------
def register_handlers(app):
    """تسجيل جميع المعالجات."""
    # الأوامر الأساسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("settings", settings))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("premium", premium))
    app.add_handler(CommandHandler("unpremium", unpremium))
    app.add_handler(CommandHandler("maintenance", maintenance_cmd))
    app.add_handler(CommandHandler("channels", list_channels))
    
    # معالج callback للاشتراك
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    
    # معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
