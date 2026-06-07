# subscription.py
"""
نظام الاشتراك الإجباري لقناة BEXO50
"""

import logging
from typing import Optional, Tuple, List
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# ✅ تفعيل الاشتراك الإجباري لقناة BEXO50
REQUIRED_CHANNELS = [
    {
        "name": "BEXO50",
        "username": "BEXO50",  # بدون @
        "url": "https://t.me/BEXO50"
    }
]

async def check_user_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[dict]]:
    """
    يتحقق من اشتراك المستخدم في جميع القنوات المطلوبة.
    يعيد (جميع_القنوات_مشترك, قائمة_القنوات_غير_المشترك_فيها)
    """
    if not REQUIRED_CHANNELS:
        return True, []
    
    unsubscribed = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            chat_member = await bot.get_chat_member(
                chat_id=f"@{channel['username']}", 
                user_id=user_id
            )
            # الحالات التي تعني أن المستخدم مشترك: member, administrator, creator
            if chat_member.status in ['left', 'kicked']:
                unsubscribed.append(channel)
        except TelegramError as e:
            logger.warning(f"Cannot check subscription for {channel['username']}: {e}")
            # إذا حدث خطأ (مثل البوت ليس أدمن في القناة)، نعتبره غير مشترك
            unsubscribed.append(channel)
    
    return len(unsubscribed) == 0, unsubscribed


def get_subscription_keyboard(unsubscribed_channels: List[dict]) -> InlineKeyboardMarkup:
    """
    ينشئ أزرار للاشتراك في القنوات غير المشترك فيها.
    """
    keyboard = []
    
    for channel in unsubscribed_channels:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 اشترك في {channel['name']}",
                url=channel['url']
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="✅ تحققت من الاشتراك",
            callback_data="check_subscription"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def send_subscription_message(update, unsubscribed_channels: List[dict]):
    """
    يرسل رسالة تطلب من المستخدم الاشتراك في القنوات.
    """
    text = "🔒 *مطلوب الاشتراك في القناة لاستخدام البوت*\n\n"
    text += "لا يمكنك استخدام البوت حتى تشترك في القنوات التالية:\n\n"
    
    for channel in unsubscribed_channels:
        text += f"• [{channel['name']}]({channel['url']})\n"
    
    text += "\n⬅️ بعد الاشتراك، اضغط زر التحقق"
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_subscription_keyboard(unsubscribed_channels),
        disable_web_page_preview=True
    )
