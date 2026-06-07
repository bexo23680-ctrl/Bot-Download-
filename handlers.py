"""
معالجات بوت تيليجرام مع أزرار تفاعلية
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

# تخزين مهام التحميل النشطة
active_downloads: dict = {}

def set_shared_objects(database: Database, dl: Downloader):
    """ربط قاعدة البيانات والتنزيل مع المعالجات."""
    global db, downloader
    db = database
    downloader = dl

# -------------------------------
# دالة مساعدة: التحقق من وضع الصيانة
# -------------------------------
async def is_maintenance(user_id: int) -> bool:
    """التحقق مما إذا كان البوت في وضع الصيانة."""
    if MAINTENANCE_MODE and user_id not in ADMINS:
        return True
    return False

# -------------------------------
# لوحة التحكم الرئيسية (الأزرار)
# -------------------------------
def get_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """إنشاء أزرار القائمة الرئيسية"""
    keyboard = [
        [
            InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="my_settings"),
        ],
        [
            InlineKeyboardButton("❓ المساعدة", callback_data="help"),
            InlineKeyboardButton("📞 معلومات الأدمن", callback_data="admin_info"),
        ],
        [
            InlineKeyboardButton("💎 الترقية إلى بريميوم", callback_data="upgrade_premium"),
        ]
    ]
    
    # إذا كان المستخدم أدمن، أضف زر لوحة الأدمن
    if user_id and user_id in ADMINS:
        keyboard.append([
            InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel"),
        ])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """إنشاء أزرار لوحة الأدمن"""
    keyboard = [
        [
            InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast"),
            InlineKeyboardButton("➕ منح بريميوم", callback_data="admin_add_premium"),
        ],
        [
            InlineKeyboardButton("➖ إزالة بريميوم", callback_data="admin_remove_premium"),
            InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban"),
        ],
        [
            InlineKeyboardButton("✅ فك حظر", callback_data="admin_unban"),
            InlineKeyboardButton("🛠️ وضع الصيانة", callback_data="admin_maintenance"),
        ],
        [
            InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """زر إلغاء"""
    keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """زر رجوع"""
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(keyboard)

def get_maintenance_keyboard() -> InlineKeyboardMarkup:
    """أزرار وضع الصيانة"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 تفعيل", callback_data="maintenance_on"),
            InlineKeyboardButton("🔴 إيقاف", callback_data="maintenance_off"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------------
# معالجات الأوامر الأساسية
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية مع أزرار"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"✅ Start command from user: {user_id}")
    
    try:
        # إضافة المستخدم لقاعدة البيانات
        if db:
            await db.add_or_update_user(
                user_id, 
                user.username or "", 
                user.first_name or "", 
                user.last_name or ""
            )
        
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
        
    except Exception as e:
        logger.error(f"Error in start: {e}")
        await update.message.reply_text(
            "✅ *البوت يعمل بشكل طبيعي!*\n\n"
            "أرسل رابط انستغرام للبدء في التحميل.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )

# -------------------------------
# معالج الأزرار (Callback Query)
# -------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج جميع الأزرار"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    # ========== الأزرار الرئيسية ==========
    
    if data == "my_stats":
        # عرض الإحصائيات
        user_data = await db.get_user(user_id)
        if not user_data:
            await query.message.reply_text("📭 لا توجد بيانات بعد. أرسل رابطاً أولاً!")
            return
        
        total = user_data['total_downloads']
        premium = "✅ مفعل" if user_data['is_premium'] else "❌ غير مفعل"
        daily = await db.get_daily_count(user_id)
        limit = "∞ غير محدود" if user_data['is_premium'] else str(DAILY_LIMIT_NON_PREMIUM)
        
        await query.message.reply_text(
            f"📊 *إحصائياتك*\n\n"
            f"📥 إجمالي التحميلات: {total}\n"
            f"📅 تحميلات اليوم: {daily}/{limit}\n"
            f"💎 البريميوم: {premium}\n\n"
            f"🔙 استخدم الزر أدناه للرجوع:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "my_settings":
        # عرض الإعدادات
        user_data = await db.get_user(user_id)
        premium = user_data['is_premium'] if user_data else False
        
        if premium:
            text = (
                "⚙️ *الإعدادات*\n\n"
                "💎 *حالتك:* بريميوم ✅\n"
                "📥 التحميل: غير محدود\n"
                "⭐ أنت مشترك مميز!\n\n"
                "🔙 استخدم الزر أدناه للرجوع:"
            )
        else:
            text = (
                "⚙️ *الإعدادات*\n\n"
                "🆓 *حالتك:* مجاني\n"
                f"📥 الحد اليومي: {DAILY_LIMIT_NON_PREMIUM} تحميلات\n\n"
                "💎 *للترقية إلى بريميوم:*\n"
                "تواصل مع الأدمن @pngo1\n\n"
                "🔙 استخدم الزر أدناه للرجوع:"
            )
        
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "help":
        # عرض المساعدة
        await query.message.reply_text(
            "📘 *كيفية استخدام البوت:*\n\n"
            "1️⃣ انسخ رابط منشور انستغرام عام\n"
            "2️⃣ أرسل الرابط إلى البوت\n"
            "3️⃣ انتظر حتى يتم التحميل والإرسال\n\n"
            "⚠️ *شروط الاستخدام:*\n"
            "• يجب أن يكون الحساب *عاماً*\n"
            "• الروابط المدعومة: `/p/` , `/reel/` , `/tv/`\n\n"
            f"💎 *البريميوم:* تحميل غير محدود\n"
            f"🆓 *المجاني:* {DAILY_LIMIT_NON_PREMIUM} تحميلات يومياً\n\n"
            "🔙 استخدم الزر أدناه للرجوع:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_info":
        # معلومات الأدمن
        await query.message.reply_text(
            "📞 *معلومات التواصل*\n\n"
            "👤 *الأدمن:* @pngo1\n\n"
            "للاستفسارات:\n"
            "• طلب الترقية إلى بريميوم\n"
            "• الدعم الفني\n"
            "• الإبلاغ عن مشاكل\n\n"
            "🔙 استخدم الزر أدناه للرجوع:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "upgrade_premium":
        # الترقية
        await query.message.reply_text(
            "💎 *الترقية إلى بريميوم*\n\n"
            "مميزات البريميوم:\n"
            "✅ تحميل غير محدود يومياً\n"
            "✅ أولوية في المعالجة\n"
            "✅ دعم فني مباشر\n\n"
            "📞 *للترقية:* تواصل مع الأدمن @pngo1\n\n"
            "💰 *السعر:* يرجى التواصل لمعرفة التفاصيل\n\n"
            "🔙 استخدم الزر أدناه للرجوع:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "back_to_main":
        # رجوع للقائمة الرئيسية
        await query.message.edit_text(
            "🏠 *القائمة الرئيسية*\n\nاختر من الأزرار أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
    
    # ========== أزرار الأدمن ==========
    
    elif data == "admin_panel":
        if user_id not in ADMINS:
            await query.message.reply_text("⛔ هذا الأمر للمشرفين فقط")
            return
        
        await query.message.reply_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر الإجراء المطلوب:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    elif data == "back_to_admin":
        await query.message.edit_text(
            "👑 *لوحة تحكم الأدمن*\n\nاختر الإجراء المطلوب:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    elif data == "admin_stats":
        if user_id not in ADMINS:
            return
        
        total_users, premium_users, total_downloads = await db.get_stats()
        await query.message.reply_text(
            f"📊 *إحصائيات البوت*\n\n"
            f"👥 إجمالي المستخدمين: {total_users}\n"
            f"💎 المشتركين المميزين: {premium_users}\n"
            f"📥 إجمالي التحميلات: {total_downloads}\n\n"
            f"📅 آخر تحديث: الآن",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_maintenance":
        if user_id not in ADMINS:
            return
        
        await query.message.reply_text(
            "🛠️ *وضع الصيانة*\n\nاختر الحالة:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_maintenance_keyboard()
        )
    
    elif data == "maintenance_on":
        if user_id not in ADMINS:
            return
        
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = True
        await query.message.reply_text(
            "🛠️ *تم تفعيل وضع الصيانة*\n\n"
            "المستخدمون العاديون لن يتمكنوا من استخدام البوت.",
            reply_markup=get_back_keyboard()
        )
    
    elif data == "maintenance_off":
        if user_id not in ADMINS:
            return
        
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = False
        await query.message.reply_text(
            "✅ *تم إيقاف وضع الصيانة*\n\n"
            "البوت يعمل بشكل طبيعي الآن.",
            reply_markup=get_back_keyboard()
        )
    
    elif data == "admin_ban":
        if user_id not in ADMINS:
            return
        
        context.user_data['admin_action'] = 'ban'
        await query.message.reply_text(
            "🚫 *حظر مستخدم*\n\n"
            "أرسل معرف المستخدم (user_id) لحظره:\n"
            "مثال: `123456789`\n\n"
            "لإلغاء العملية اضغط الزر أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    
    elif data == "admin_unban":
        if user_id not in ADMINS:
            return
        
        context.user_data['admin_action'] = 'unban'
        await query.message.reply_text(
            "✅ *فك الحظر*\n\n"
            "أرسل معرف المستخدم لفك حظره:\n"
            "مثال: `123456789`\n\n"
            "لإلغاء العملية اضغط الزر أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    
    elif data == "admin_add_premium":
        if user_id not in ADMINS:
            return
        
        context.user_data['admin_action'] = 'add_premium'
        await query.message.reply_text(
            "💎 *منح بريميوم*\n\n"
            "أرسل معرف المستخدم لمنحه بريميوم:\n"
            "مثال: `123456789`\n\n"
            "لإلغاء العملية اضغط الزر أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    
    elif data == "admin_remove_premium":
        if user_id not in ADMINS:
            return
        
        context.user_data['admin_action'] = 'remove_premium'
        await query.message.reply_text(
            "💔 *إزالة بريميوم*\n\n"
            "أرسل معرف المستخدم لإزالة بريميوم:\n"
            "مثال: `123456789`\n\n"
            "لإلغاء العملية اضغط الزر أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    
    elif data == "admin_broadcast":
        if user_id not in ADMINS:
            return
        
        context.user_data['admin_action'] = 'broadcast'
        await query.message.reply_text(
            "📢 *إرسال إشعار للجميع*\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:\n\n"
            "لإلغاء العملية اضغط الزر أدناه:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    
    elif data == "cancel":
        context.user_data.pop('admin_action', None)
        await query.message.reply_text(
            "❌ *تم الإلغاء*",
            reply_markup=get_back_keyboard()
        )

# -------------------------------
# معالج الرسائل النصية للأدمن
# -------------------------------
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية من الأدمن (لإدخال IDs والرسائل)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS:
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    text = update.message.text.strip()
    
    if action == 'ban':
        try:
            uid = int(text)
            await db.set_ban(uid, True)
            await update.message.reply_text(f"✅ تم حظر المستخدم `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
        context.user_data.pop('admin_action', None)
    
    elif action == 'unban':
        try:
            uid = int(text)
            await db.set_ban(uid, False)
            await update.message.reply_text(f"✅ تم فك الحظر عن `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
        context.user_data.pop('admin_action', None)
    
    elif action == 'add_premium':
        try:
            uid = int(text)
            await db.set_premium(uid, True)
            await update.message.reply_text(f"✅ تم منح بريميوم للمستخدم `{uid}`", parse_mode=ParseMode.MARKDOWN)
            try:
                await context.bot.send_message(uid, "🎉 تمت ترقيتك إلى بريميوم!")
            except:
                pass
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
        context.user_data.pop('admin_action', None)
    
    elif action == 'remove_premium':
        try:
            uid = int(text)
            await db.set_premium(uid, False)
            await update.message.reply_text(f"✅ تم إزالة بريميوم عن المستخدم `{uid}`", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ معرف غير صالح")
        context.user_data.pop('admin_action', None)
    
    elif action == 'broadcast':
        # إرسال رسالة لجميع المستخدمين
        confirm_msg = await update.message.reply_text("📢 جاري إرسال الرسالة...")
        
        async with db._conn.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
            users = await cursor.fetchall()
        
        count = 0
        failed = 0
        for (uid,) in users:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"📢 *رسالة من الإدارة:*\n\n{text}\n\n📞 للتواصل: @pngo1",
                    parse_mode=ParseMode.MARKDOWN
                )
                count += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        
        await confirm_msg.edit_text(f"✅ تم الإرسال!\n📤 نجح: {count}\n❌ فشل: {failed}")
        context.user_data.pop('admin_action', None)

# -------------------------------
# معالج الرسائل (رابط انستغرام)
# -------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الرئيسي للروابط"""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    # إذا كان الأدمن في وضع إدخال نصي
    if user_id in ADMINS and context.user_data.get('admin_action'):
        await handle_admin_text(update, context)
        return

    # فحص وضع الصيانة
    if await is_maintenance(user_id):
        await update.message.reply_text(
            "🛠️ *البوت في وضع الصيانة*\nنعمل على تحسين الخدمة حالياً.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # التحقق من صحة الرابط
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

    # باقي كود التحميل كما هو...
    # (نفس الكود السابق لتحميل الملفات)
    
    # مؤقت للإجابة
    await update.message.reply_text("⏳ جاري معالجة الرابط...")

# -------------------------------
# تسجيل جميع المعالجات
# -------------------------------
def register_handlers(app):
    """تسجيل جميع معالجات البوت."""
    
    # الأوامر الأساسية
    app.add_handler(CommandHandler("hi", start))
    
    # معالج الأزرار
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل النصية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ تم تسجيل جميع المعالجات مع الأزرار بنجاح")
