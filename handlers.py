"""
معالجات بوت تيليجرام مع أزرار تفاعلية - النسخة الكاملة
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

logger = logging.getLogger(__name__)

db: Optional[Database] = None
downloader: Optional[Downloader] = None
active_downloads: dict = {}

def set_shared_objects(database: Database, dl: Downloader):
    """ربط قاعدة البيانات والتنزيل مع المعالجات."""
    global db, downloader
    db = database
    downloader = dl

# -------------------------------
# دوال مساعدة
# -------------------------------
async def is_maintenance(user_id: int) -> bool:
    """التحقق مما إذا كان البوت في وضع الصيانة."""
    if MAINTENANCE_MODE and user_id not in ADMINS:
        return True
    return False

# -------------------------------
# لوحات المفاتيح (Keyboards)
# -------------------------------
def get_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """إنشاء أزرار القائمة الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="my_settings")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="help"),
         InlineKeyboardButton("📞 معلومات الأدمن", callback_data="admin_info")],
        [InlineKeyboardButton("💎 الترقية إلى بريميوم", callback_data="upgrade_premium")],
    ]
    if user_id and user_id in ADMINS:
        keyboard.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """إنشاء أزرار لوحة الأدمن"""
    keyboard = [
        [InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast"),
         InlineKeyboardButton("➕ منح بريميوم", callback_data="admin_add_premium")],
        [InlineKeyboardButton("➖ إزالة بريميوم", callback_data="admin_remove_premium"),
         InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ فك حظر", callback_data="admin_unban"),
         InlineKeyboardButton("🛠️ وضع الصيانة", callback_data="admin_maintenance")],
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """زر رجوع"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """زر إلغاء"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]])

def get_maintenance_keyboard() -> InlineKeyboardMarkup:
    """أزرار وضع الصيانة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 تفعيل", callback_data="maintenance_on"),
         InlineKeyboardButton("🔴 إيقاف", callback_data="maintenance_off")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin")],
    ])

# -------------------------------
# أمر البداية
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية مع أزرار"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"✅ Start command from user: {user_id}")
    
    # إضافة المستخدم لقاعدة البيانات
    try:
        await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
    except Exception as e:
        logger.error(f"Error adding user: {e}")
    
    # رسالة الترحيب مع الأزرار
    await update.message.reply_text(
        "👋 *مرحباً بك في بوت تحميل انستغرام!*\n\n"
        "✨ *المميزات:*\n"
        "• تحميل فيديوهات وصور انستغرام\n"
        "• دعم الريلز والمنشورات المتعددة\n"
        "• جودة عالية\n\n"
        "📤 *كيفية الاستخدام:*\n"
        "أرسل رابط انستغرام وسأقوم بتحميله لك فوراً\n\n"
        "💡 اختر من الأزرار أدناه:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user_id)
    )

# -------------------------------
# معالج الأزرار
# -------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج جميع الأزرار"""
    global MAINTENANCE_MODE  # ✅ تم نقلها إلى بداية الدالة
    
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    # ========== الأزرار الرئيسية ==========
    
    if data == "my_stats":
        user_data = await db.get_user(user_id)
        if not user_data:
            await query.message.edit_text(
                "📭 لا توجد بيانات بعد. أرسل رابطاً أولاً!",
                reply_markup=get_back_keyboard()
            )
            return
        
        total = user_data['total_downloads']
        premium = "✅ مفعل" if user_data['is_premium'] else "❌ غير مفعل"
        daily = await db.get_daily_count(user_id)
        limit = "∞ غير محدود" if user_data['is_premium'] else str(DAILY_LIMIT_NON_PREMIUM)
        
        await query.message.edit_text(
            f"📊 *إحصائياتك*\n\n"
            f"📥 إجمالي التحميلات: {total}\n"
            f"📅 تحميلات اليوم: {daily}/{limit}\n"
            f"💎 البريميوم: {premium}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "my_settings":
        user_data = await db.get_user(user_id)
        premium = user_data['is_premium'] if user_data else False
        
        if premium:
            text = "⚙️ *الإعدادات*\n\n💎 *حالتك:* بريميوم ✅\n📥 التحميل: غير محدود\n⭐ أنت مشترك مميز!"
        else:
            text = (
                "⚙️ *الإعدادات*\n\n"
                "🆓 *حالتك:* مجاني\n"
                f"📥 الحد اليومي: {DAILY_LIMIT_NON_PREMIUM} تحميلات\n\n"
                "💎 *للترقية:* تواصل مع @pngo1"
            )
        
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_back_keyboard())
    
    elif data == "help":
        await query.message.edit_text(
            "📘 *كيفية استخدام البوت:*\n\n"
            "1️⃣ انسخ رابط منشور انستغرام عام\n"
            "2️⃣ أرسل الرابط إلى البوت\n"
            "3️⃣ انتظر حتى يتم التحميل والإرسال\n\n"
            f"💎 البريميوم: تحميل غير محدود\n"
            f"🆓 المجاني: {DAILY_LIMIT_NON_PREMIUM} تحميلات يومياً\n\n"
            "📞 للدعم: @pngo1",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_info":
        await query.message.edit_text(
            "📞 *معلومات التواصل*\n\n"
            "👤 *الأدمن:* @pngo1\n\n"
            "للاستفسارات:\n"
            "• طلب الترقية إلى بريميوم\n"
            "• الدعم الفني\n"
            "• الإبلاغ عن مشاكل",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "upgrade_premium":
        await query.message.edit_text(
            "💎 *الترقية إلى بريميوم*\n\n"
            "مميزات البريميوم:\n"
            "✅ تحميل غير محدود يومياً\n"
            "✅ أولوية في المعالجة\n"
            "✅ دعم فني مباشر\n\n"
            "📞 *للترقية:* تواصل مع @pngo1",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "back_to_main":
        await query.message.edit_text(
            "🏠 *القائمة الرئيسية*\n\nاختر من الأزرار أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
    
    # ========== أزرار الأدمن ==========
    
    elif data == "admin_panel":
        if user_id not in ADMINS:
            await query.answer("⛔ للمشرفين فقط", show_alert=True)
            return
        
        await query.message.edit_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر الإجراء المطلوب:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    elif data == "back_to_admin":
        if user_id not in ADMINS:
            return
        await query.message.edit_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر الإجراء المطلوب:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    elif data == "admin_stats":
        if user_id not in ADMINS:
            return
        total_users, premium_users, total_downloads = await db.get_stats()
        await query.message.edit_text(
            f"📊 *إحصائيات البوت*\n\n"
            f"👥 المستخدمين: {total_users}\n"
            f"💎 المميزين: {premium_users}\n"
            f"📥 التحميلات: {total_downloads}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_maintenance":
        if user_id not in ADMINS:
            return
        await query.message.edit_text(
            "🛠️ *وضع الصيانة*\n\nاختر الحالة:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_maintenance_keyboard()
        )
    
    elif data == "maintenance_on":
        if user_id not in ADMINS:
            return
        MAINTENANCE_MODE = True  # ✅ بدون global لأنها في بداية الدالة
        await query.message.edit_text(
            "🛠️ *تم تفعيل وضع الصيانة*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "maintenance_off":
        if user_id not in ADMINS:
            return
        MAINTENANCE_MODE = False  # ✅ بدون global لأنها في بداية الدالة
        await query.message.edit_text(
            "✅ *تم إيقاف وضع الصيانة*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data in ["admin_ban", "admin_unban", "admin_add_premium", "admin_remove_premium"]:
        if user_id not in ADMINS:
            return
        
        action_map = {
            "admin_ban": ("ban", "🚫 *حظر مستخدم*\n\nأرسل معرف المستخدم:"),
            "admin_unban": ("unban", "✅ *فك حظر*\n\nأرسل معرف المستخدم:"),
            "admin_add_premium": ("add_premium", "💎 *منح بريميوم*\n\nأرسل معرف المستخدم:"),
            "admin_remove_premium": ("remove_premium", "💔 *إزالة بريميوم*\n\nأرسل معرف المستخدم:"),
        }
        
        action, text = action_map[data]
        context.user_data['admin_action'] = action
        
        await query.message.edit_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
        )
    
    elif data == "admin_broadcast":
        if user_id not in ADMINS:
            return
        context.user_data['admin_action'] = 'broadcast'
        await query.message.edit_text(
            "📢 *إرسال إشعار للجميع*\n\nأرسل الرسالة التي تريد إرسالها:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
        )
    
    elif data == "cancel":
        context.user_data.pop('admin_action', None)
        await query.message.edit_text(
            "❌ *تم الإلغاء*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )

# -------------------------------
# معالج النصوص الإدارية
# -------------------------------
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النصوص من الأدمن"""
    user_id = update.effective_user.id
    action = context.user_data.get('admin_action')
    
    if not action or user_id not in ADMINS:
        return False
    
    text = update.message.text.strip()
    
    if action == 'ban':
        try:
            uid = int(text)
            await db.set_ban(uid, True)
            await update.message.reply_text(f"✅ تم حظر `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
    
    elif action == 'unban':
        try:
            uid = int(text)
            await db.set_ban(uid, False)
            await update.message.reply_text(f"✅ تم فك حظر `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
    
    elif action == 'add_premium':
        try:
            uid = int(text)
            await db.set_premium(uid, True)
            await update.message.reply_text(f"✅ تم منح بريميوم لـ `{uid}`", parse_mode=ParseMode.MARKDOWN)
            try:
                await context.bot.send_message(uid, "🎉 تمت ترقيتك إلى بريميوم!")
            except:
                pass
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
    
    elif action == 'remove_premium':
        try:
            uid = int(text)
            await db.set_premium(uid, False)
            await update.message.reply_text(f"✅ تم إزالة بريميوم من `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
    
    elif action == 'broadcast':
        confirm_msg = await update.message.reply_text("📢 جاري إرسال الرسالة...")
        
        async with db._conn.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
            users = await cursor.fetchall()
        
        count = 0
        for (uid,) in users:
            try:
                await context.bot.send_message(uid, f"📢 *رسالة من الإدارة:*\n\n{text}\n\n📞 @pngo1", parse_mode=ParseMode.MARKDOWN)
                count += 1
                await asyncio.sleep(0.05)
            except:
                pass
        
        await confirm_msg.edit_text(f"✅ تم الإرسال إلى {count} مستخدم")
    
    context.user_data.pop('admin_action', None)
    return True

# -------------------------------
# معالج الروابط
# -------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الرئيسي"""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    # إذا كان الأدمن في وضع إدخال
    if await handle_admin_text(update, context):
        return

    # فحص الصيانة
    if await is_maintenance(user_id):
        await update.message.reply_text("🛠️ *البوت في وضع الصيانة*", parse_mode=ParseMode.MARKDOWN)
        return

    # فحص الرابط
    if not is_valid_instagram_url(text):
        await update.message.reply_text(
            "❌ *رابط غير صالح!*\n\n"
            "📝 *الروابط المدعومة:*\n"
            "• `https://www.instagram.com/p/...`\n"
            "• `https://www.instagram.com/reel/...`\n"
            "• `https://www.instagram.com/tv/...`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
        return

    # فحص المعدل
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text(f"⏳ انتظر {RATE_LIMIT_WINDOW} ثانية", reply_markup=get_main_keyboard(user_id))
        return

    # تحديث قاعدة البيانات
    await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")

    # فحص الحظر
    if await db.is_banned(user_id):
        await update.message.reply_text("🚫 *أنت محظور*", parse_mode=ParseMode.MARKDOWN)
        return

    # فحص الحد اليومي
    is_prem = await db.is_premium(user_id)
    if not is_prem:
        daily = await db.get_daily_count(user_id)
        if daily >= DAILY_LIMIT_NON_PREMIUM:
            await update.message.reply_text(
                f"⛔ *وصلت للحد اليومي!*\n\n"
                f"💎 للترقية: @pngo1",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard(user_id)
            )
            return

    # بدء التحميل
    status_msg = await update.message.reply_text("⏳ *جاري تحليل الرابط...*", parse_mode=ParseMode.MARKDOWN)

    if user_id in active_downloads:
        await status_msg.edit_text("⚠️ *تحميل آخر قيد التقدم*", parse_mode=ParseMode.MARKDOWN)
        return

    active_downloads[user_id] = True

    try:
        info = await downloader.get_media_info(text)
        title = info.get('title', 'محتوى انستغرام')

        async def progress(percent: float, speed: str):
            try:
                await status_msg.edit_text(
                    f"📥 *جاري التحميل...*\n"
                    f"▕{'█' * int(percent / 10)}{'░' * (10 - int(percent / 10))}▏ {percent:.1f}%\n"
                    f"⚡ {speed}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

        files = await downloader.download(text, progress)
        await status_msg.edit_text("📤 *جاري الرفع...*", parse_mode=ParseMode.MARKDOWN)

        sent_count = 0
        for idx, filepath in enumerate(files):
            if not os.path.exists(filepath):
                continue
            
            file_size = os.path.getsize(filepath)
            if file_size > 50 * 1024 * 1024:
                await status_msg.reply_text(f"⚠️ الملف كبير جداً ({file_size / 1024 / 1024:.1f}MB)")
                continue
            
            caption = f"📌 {title}" if idx == 0 else None
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
                logger.error(f"Failed to send {filepath}: {e}")

        if sent_count > 0:
            await db.increment_downloads(user_id)
            remaining = "∞" if is_prem else str(DAILY_LIMIT_NON_PREMIUM - await db.get_daily_count(user_id) + 1)
            await status_msg.edit_text(
                f"✅ *تم التحميل!*\n📁 {sent_count} ملف\n📊 المتبقي: {remaining}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard(user_id)
            )
        else:
            await status_msg.edit_text("❌ *فشل التحميل*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(
            f"❌ *خطأ:* {str(e)[:150]}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
    finally:
        active_downloads.pop(user_id, None)
        if 'files' in locals() and files:
            parent_dir = Path(files[0]).parent if files else None
            if parent_dir and os.path.exists(parent_dir):
                import shutil
                shutil.rmtree(parent_dir)

# -------------------------------
# تسجيل المعالجات
# -------------------------------
def register_handlers(app):
    """تسجيل جميع المعالجات"""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("✅ Handlers registered")
