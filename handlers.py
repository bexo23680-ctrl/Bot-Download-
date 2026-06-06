"""
معالجات بوت تيليجرام - النسخة العربية
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
# معالجات الأوامر الأساسية
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية مع فحص الاشتراك."""
    user = update.effective_user
    user_id = user.id
    
    # إضافة المستخدم إلى قاعدة البيانات
    await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
    
    # فحص الاشتراك أولاً
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    
    if not is_subscribed:
        await send_subscription_message(update, unsubscribed)
        return
    
    # المستخدم مشترك - ترحيب
    await update.message.reply_text(
        "👋 *مرحباً بك في بوت تحميل محتوى انستغرام!*\n\n"
        "أرسل لي رابط انستغرام عام (ريلز، فيديوهات، صور، البومات) وسأقوم بتحميله بأعلى جودة.\n\n"
        "📋 *الأوامر المتاحة:*\n"
        "/start – بدء البوت\n"
        "/help – تعليمات المساعدة\n"
        "/stats – إحصائيات استخدامك\n"
        "/settings – معلومات الاشتراك\n"
        "/admin_info – معلومات الأدمن\n\n"
        "💡 *مثال:* أرسل رابط مثل:\n"
        "`https://www.instagram.com/reel/XXXXX/`",
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
        "📘 *كيفية استخدام البوت:*\n\n"
        "1️⃣ انسخ رابط منشور انستغرام عام\n"
        "2️⃣ أرسل الرابط إلى البوت\n"
        "3️⃣ انتظر حتى يتم التحميل والإرسال\n\n"
        "⚠️ *شروط الاستخدام:*\n"
        "• يجب أن يكون الحساب *عاماً*\n"
        "• الروابط المدعومة: `/p/` , `/reel/` , `/tv/`\n\n"
        f"💎 *البريميوم:* تحميل غير محدود يومياً\n"
        f"🆓 *المجاني:* {DAILY_LIMIT_NON_PREMIUM} تحميلات يومياً\n\n"
        "📞 للدعم أو الترقية، تواصل مع الأدمن:\n"
        "@pngo1",
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
        await update.message.reply_text("📭 لا توجد بيانات بعد. أرسل رابطاً أولاً!")
        return
    
    total = user_data['total_downloads']
    premium = "✅ مفعل" if user_data['is_premium'] else "❌ غير مفعل"
    daily = await db.get_daily_count(user_id)
    limit = "∞ غير محدود" if user_data['is_premium'] else str(DAILY_LIMIT_NON_PREMIUM)
    
    await update.message.reply_text(
        f"📊 *إحصائياتك*\n\n"
        f"📥 إجمالي التحميلات: {total}\n"
        f"📅 تحميلات اليوم: {daily}/{limit}\n"
        f"💎 البريميوم: {premium}\n\n"
        f"⚙️ استخدم /settings لإدارة الاشتراك.\n"
        f"📞 للترقية: @pngo1",
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
    
    if premium:
        text = (
            "⚙️ *الإعدادات*\n\n"
            "💎 *حالتك:* بريميوم ✅\n"
            "📥 التحميل: غير محدود\n"
            "⭐ أنت مشترك مميز!\n\n"
            "📞 للأستفسار: @pngo1"
        )
    else:
        text = (
            "⚙️ *الإعدادات*\n\n"
            "🆓 *حالتك:* مجاني\n"
            f"📥 الحد اليومي: {DAILY_LIMIT_NON_PREMIUM} تحميلات\n\n"
            "💎 *للترقية إلى بريميوم:*\n"
            "تواصل مع الأدمن:\n"
            "@pngo1\n\n"
            "المميزات:\n"
            "• تحميل غير محدود\n"
            "• أولوية في المعالجة\n"
            "• دعم فني مباشر"
        )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def admin_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الأدمن للتواصل."""
    await update.message.reply_text(
        "📞 *معلومات التواصل*\n\n"
        "👤 *الأدمن:* @pngo1\n\n"
        "للاستفسارات:\n"
        "• طلب الترقية إلى بريميوم\n"
        "• الدعم الفني\n"
        "• الإبلاغ عن مشاكل\n"
        "• الاقتراحات\n\n"
        "💬 تواصل مع الأدمن مباشرة عبر المعرف أعلاه.",
        parse_mode=ParseMode.MARKDOWN
    )

# -------------------------------
# معالج أزرار الاشتراك
# -------------------------------
async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الضغط على زر التحقق من الاشتراك."""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # التحقق من الاشتراك مرة أخرى
    is_subscribed, unsubscribed = await check_user_subscription(context.bot, user_id)
    
    if is_subscribed:
        # حذف رسالة الاشتراك
        try:
            await query.message.delete()
        except:
            pass
        
        # إرسال رسالة ترحيب
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 *تم التحقق بنجاح!*\n\n"
                "✅ أنت مشترك الآن في جميع القنوات المطلوبة.\n"
                "🚀 يمكنك الآن استخدام البوت بحرية.\n\n"
                "📤 أرسل رابط انستغرام للتحميل.\n"
                "📖 للمساعدة: /help"
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
            "📢 اشترك في القنوات أعلاه ثم اضغط على الزر أدناه 👇"
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
            logger.error(f"خطأ في تحديث رسالة الاشتراك: {e}")

# -------------------------------
# معالج الرسائل (رابط انستغرام)
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

    # فحص وضع الصيانة
    if await is_maintenance(user_id):
        await update.message.reply_text(
            "🛠️ *البوت في وضع الصيانة*\n\n"
            "نعمل على تحسين الخدمة حالياً.\n"
            "يرجى المحاولة لاحقاً.",
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
            "• `https://www.instagram.com/tv/...`\n\n"
            "تأكد أن الرابط لمنشور *عام* وليس خاص.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # فحص الحد الأقصى للطلبات
    if not rate_limiter.is_allowed(user_id):
        wait = RATE_LIMIT_WINDOW
        await update.message.reply_text(
            f"⏳ *طلبات كثيرة جداً!*\n\n"
            f"يرجى الانتظار {wait} ثانية قبل المحاولة مجدداً.\n"
            f"💎 المستخدمين المميزين لديهم أولوية أعلى.\n"
            f"📞 للترقية: @pngo1",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # تحديث بيانات المستخدم
    await db.add_or_update_user(user_id, user.username or "", user.first_name or "", user.last_name or "")

    # فحص الحظر
    if await db.is_banned(user_id):
        await update.message.reply_text(
            "🚫 *أنت محظور من استخدام البوت*\n\n"
            "إذا كنت تعتقد أن هذا خطأ، تواصل مع الأدمن:\n"
            "@pngo1",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # فحص الحد اليومي
    is_prem = await db.is_premium(user_id)
    if not is_prem:
        daily = await db.get_daily_count(user_id)
        if daily >= DAILY_LIMIT_NON_PREMIUM:
            await update.message.reply_text(
                f"⛔ *وصلت للحد اليومي!*\n\n"
                f"لقد استخدمت {DAILY_LIMIT_NON_PREMIUM}/{DAILY_LIMIT_NON_PREMIUM} تحميلات اليوم.\n\n"
                f"💎 *للحصول على تحميل غير محدود:*\n"
                f"• تواصل مع الأدمن: @pngo1\n"
                f"• استخدم /settings للمزيد من المعلومات",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # بدء عملية التحميل
    status_msg = await update.message.reply_text("⏳ *جاري تحليل الرابط...*", parse_mode=ParseMode.MARKDOWN)

    if user_id in active_downloads:
        await status_msg.edit_text(
            "⚠️ *تحميل آخر قيد التقدم*\n"
            "يرجى الانتظار حتى يكتمل التحميل الحالي.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    active_downloads[user_id] = True

    try:
        # 1. استخراج معلومات الميديا
        info = await downloader.get_media_info(text)
        media_type = info.get('type', 'unknown')
        title = info.get('title', 'محتوى انستغرام')
        
        # ترجمة نوع الميديا
        media_type_ar = {
            'video': '🎬 فيديو',
            'photo': '🖼️ صورة',
            'carousel': '📚 البوم'
        }.get(media_type, '📎 محتوى')

        # 2. دالة تحديث التقدم
        async def progress(percent: float, speed: str):
            try:
                await status_msg.edit_text(
                    f"📥 *جاري التحميل...*\n"
                    f"▕{'█' * int(percent / 10)}{'░' * (10 - int(percent / 10))}▏ {percent:.1f}%\n"
                    f"⚡ السرعة: {speed}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

        # 3. تحميل الميديا
        files = await downloader.download(text, progress)

        # 4. إرسال الملفات
        await status_msg.edit_text(
            "📤 *جاري الرفع إلى تيليجرام...*",
            parse_mode=ParseMode.MARKDOWN
        )

        sent_count = 0
        for idx, filepath in enumerate(files):
            if not os.path.exists(filepath):
                logger.warning(f"الملف غير موجود، تخطي: {filepath}")
                continue
            
            file_size = os.path.getsize(filepath)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await status_msg.reply_text(
                    f"⚠️ *الملف كبير جداً!*\n"
                    f"الحجم: {file_size / 1024 / 1024:.1f}MB\n"
                    f"الحد الأقصى: 50MB",
                    parse_mode=ParseMode.MARKDOWN
                )
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
                logger.error(f"فشل إرسال الملف {filepath}: {e}")
                await status_msg.reply_text(
                    f"⚠️ فشل إرسال: {os.path.basename(filepath)}"
                )

        if sent_count == 0:
            await status_msg.edit_text(
                "❌ *فشل إرسال الملفات*\n"
                "يرجى المحاولة مرة أخرى.\n"
                "📞 للدعم: @pngo1",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await db.increment_downloads(user_id)
            
            # رسالة نجاح مع إحصائيات
            remaining = "∞" if is_prem else str(DAILY_LIMIT_NON_PREMIUM - await db.get_daily_count(user_id) + 1)
            await status_msg.edit_text(
                f"✅ *تم التحميل بنجاح!*\n\n"
                f"📁 عدد الملفات: {sent_count}\n"
                f"📊 المتبقي اليوم: {remaining}\n"
                f"{'💎 أنت مشترك بريميوم' if is_prem else '🆓 حساب مجاني'}\n\n"
                f"📥 أرسل رابطاً آخر للتحميل.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        logger.error(f"خطأ في معالجة {text}: {e}")
        await status_msg.edit_text(
            f"❌ *حدث خطأ!*\n\n"
            f"`{str(e)[:150]}`\n\n"
            f"🔍 *تأكد من:*\n"
            f"• الرابط صحيح وعام\n"
            f"• المنشور غير محذوف\n"
            f"• الحساب ليس خاصاً\n\n"
            f"🔄 حاول مرة أخرى أو تواصل مع الدعم:\n"
            f"@pngo1",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        active_downloads.pop(user_id, None)
        # تنظيف الملفات المؤقتة
        if 'files' in locals() and files:
            parent_dir = Path(files[0]).parent if files else None
            if parent_dir and os.path.exists(parent_dir):
                try:
                    import shutil
                    shutil.rmtree(parent_dir)
                except Exception as e:
                    logger.warning(f"فشل تنظيف الملفات: {e}")

# -------------------------------
# أوامر الأدمن
# -------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم الأدمن."""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text(
            "⛔ *للمشرفين فقط*\n\n"
            "إذا كنت تعتقد أن هذا خطأ، تواصل مع:\n"
            "@pngo1",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    total_users, premium_users, total_downloads = await db.get_stats()
    await update.message.reply_text(
        f"👑 *لوحة تحكم الأدمن*\n\n"
        f"👤 الأدمن: @pngo1\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"💎 المشتركين المميزين: {premium_users}\n"
        f"📥 إجمالي التحميلات: {total_downloads}\n\n"
        f"📋 *الأوامر المتاحة:*\n\n"
        f"👥 *إدارة المستخدمين:*\n"
        f"/ban <id> – حظر مستخدم\n"
        f"/unban <id> – فك الحظر\n"
        f"/premium <id> – منح بريميوم\n"
        f"/unpremium <id> – إزالة بريميوم\n\n"
        f"📢 *إدارة البوت:*\n"
        f"/broadcast <نص> – رسالة للجميع\n"
        f"/maintenance on/off – وضع الصيانة\n"
        f"/channels – عرض القنوات الإجبارية",
        parse_mode=ParseMode.MARKDOWN
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة لجميع المستخدمين."""
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 *طريقة الاستخدام:*\n`/broadcast <الرسالة>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    msg = ' '.join(context.args)
    
    # إرسال رسالة تأكيد للأدمن
    confirm_msg = await update.message.reply_text(
        f"📢 *جاري إرسال الرسالة...*\n\n"
        f"الرسالة: {msg[:100]}...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    async with db._conn.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
        users = await cursor.fetchall()
    
    count = 0
    failed = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *رسالة من الإدارة:*\n\n{msg}\n\n📞 للتواصل: @pngo1",
                parse_mode=ParseMode.MARKDOWN
            )
            count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"فشل الإرسال إلى {uid}: {e}")
    
    await confirm_msg.edit_text(
        f"✅ *تم الإرسال بنجاح!*\n\n"
        f"📤 تم الإرسال: {count}\n"
        f"❌ فشل: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر مستخدم."""
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args:
        await update.message.reply_text("📝 `/ban <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ معرف غير صالح")
        return
    
    await db.set_ban(uid, True)
    await update.message.reply_text(
        f"🚫 *تم حظر المستخدم:* `{uid}`\n\n"
        f"للمراجعة: @pngo1",
        parse_mode=ParseMode.MARKDOWN
    )

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فك حظر مستخدم."""
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args:
        await update.message.reply_text("📝 `/unban <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ معرف غير صالح")
        return
    
    await db.set_ban(uid, False)
    await update.message.reply_text(
        f"✅ *تم فك الحظر:* `{uid}`\n\n"
        f"للمراجعة: @pngo1",
        parse_mode=ParseMode.MARKDOWN
    )

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منح بريميوم."""
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args:
        await update.message.reply_text("📝 `/premium <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ معرف غير صالح")
        return
    
    await db.set_premium(uid, True)
    
    # إشعار المستخدم
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "🎉 *تهانينا!*\n\n"
                "تمت ترقيتك إلى *بريميوم*.\n"
                "الآن يمكنك التحميل بدون حدود يومية.\n\n"
                "📞 للدعم: @pngo1"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    await update.message.reply_text(
        f"💎 *تم منح بريميوم:* `{uid}`\n\n"
        f"تم إشعار المستخدم.",
        parse_mode=ParseMode.MARKDOWN
    )

async def unpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة بريميوم."""
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args:
        await update.message.reply_text("📝 `/unpremium <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ معرف غير صالح")
        return
    
    await db.set_premium(uid, False)
    await update.message.reply_text(
        f"💔 *تم إزالة بريميوم:* `{uid}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def maintenance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل/إيقاف وضع الصيانة."""
    global MAINTENANCE_MODE
    
    if update.effective_user.id not in ADMINS:
        return
    
    if not context.args or context.args[0].lower() not in ('on', 'off'):
        await update.message.reply_text(
            "📝 *طريقة الاستخدام:*\n`/maintenance on` – تفعيل\n`/maintenance off` – إيقاف",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    new_state = context.args[0].lower() == 'on'
    MAINTENANCE_MODE = new_state
    
    if new_state:
        await update.message.reply_text(
            "🛠️ *تم تفعيل وضع الصيانة*\n\n"
            "• المستخدمون العاديون: لن يستطيعوا استخدام البوت\n"
            "• المشرفون: يمكنهم استخدام البوت\n\n"
            "👤 الأدمن: @pngo1",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "✅ *تم إيقاف وضع الصيانة*\n"
            "عاد البوت للعمل بشكل طبيعي.\n\n"
            "👤 الأدمن: @pngo1",
            parse_mode=ParseMode.MARKDOWN
        )

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القنوات الإجبارية الحالية."""
    if update.effective_user.id not in ADMINS:
        return
    
    from subscription import REQUIRED_CHANNELS
    
    text = "*📢 القنوات الإجبارية للاشتراك:*\n\n"
    for i, ch in enumerate(REQUIRED_CHANNELS, 1):
        text += f"{i}. {ch['name']}\n   {ch['username']}\n\n"
    
    text += "🔄 لتعديل القنوات، افتح ملف `subscription.py`"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# -------------------------------
# تسجيل جميع المعالجات
# -------------------------------
def register_handlers(app):
    """تسجيل جميع معالجات البوت."""
    
    # الأوامر الأساسية للمستخدمين
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("admin_info", admin_info))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("premium", premium))
    app.add_handler(CommandHandler("unpremium", unpremium))
    app.add_handler(CommandHandler("maintenance", maintenance_cmd))
    app.add_handler(CommandHandler("channels", list_channels))
    
    # معالج أزرار الاشتراك
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    
    # معالج الرسائل النصية (روابط انستغرام)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ تم تسجيل جميع المعالجات بنجاح")
