"""
نظام الاشتراك الإجباري - معطل حالياً
"""

import logging
from typing import Optional, Tuple, List
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# قائمة القنوات الإجبارية - فارغة (تم تعطيل الاشتراك الإجباري)
REQUIRED_CHANNELS = []

async def check_user_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[dict]]:
    """
    يتحقق من اشتراك المستخدم في جميع القنوات المطلوبة.
    معطل حالياً - يعيد True دائماً.
    """
    # تم تعطيل نظام الاشتراك الإجباري
    return True, []


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
    # هذه الدالة لن تُستخدم حالياً لأن check_user_subscription تعيد True دائماً
    pass
