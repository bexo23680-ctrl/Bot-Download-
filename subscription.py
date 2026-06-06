"""
نظام الاشتراك الإجباري - يجب على المستخدم الاشتراك في القناة المحددة.
"""

import logging
from typing import Optional, Tuple
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# قائمة القنوات الإجبارية
REQUIRED_CHANNELS = [
    {
        'username': '@BEXO50',           # اسم القناة مع @
        'chat_id': '@BEXO50',            # للمقارنة
        'name': 'قناة BEXO50',          # اسم العرض
        'url': 'https://t.me/BEXO50',   # رابط القناة
    },
    # يمكنك إضافة قنوات أخرى هنا
    # {
    #     'username': '@CHANNEL2',
    #     'chat_id': '@CHANNEL2',
    #     'name': 'القناة الثانية',
    #     'url': 'https://t.me/CHANNEL2',
    # },
]

async def check_user_subscription(bot: Bot, user_id: int) -> Tuple[bool, list]:
    """
    يتحقق من اشتراك المستخدم في جميع القنوات المطلوبة.
    
    Returns:
        (is_subscribed, list_of_unsubscribed_channels)
    """
    unsubscribed = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            # التحقق من عضوية المستخدم في القناة
            member = await bot.get_chat_member(
                chat_id=channel['chat_id'],
                user_id=user_id
            )
            
            # حالات العضوية المقبولة
            allowed_statuses = ['creator', 'administrator', 'member']
            
            if member.status not in allowed_statuses:
                unsubscribed.append(channel)
                logger.info(f"User {user_id} not subscribed to {channel['username']}")
            
        except TelegramError as e:
            # إذا حدث خطأ (القناة غير موجودة، البوت ليس أدمن...)
            logger.error(f"Error checking subscription for {channel['username']}: {e}")
            # نعتبر المستخدم غير مشترك في حالة الخطأ
            unsubscribed.append(channel)
    
    is_subscribed = len(unsubscribed) == 0
    return is_subscribed, unsubscribed


def get_subscription_keyboard(unsubscribed_channels: list) -> InlineKeyboardMarkup:
    """
    ينشئ أزرار للاشتراك في القنوات غير المشترك فيها.
    """
    keyboard = []
    
    # زر لكل قناة
    for channel in unsubscribed_channels:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 اشترك في {channel['name']}",
                url=channel['url']
            )
        ])
    
    # زر التحقق من الاشتراك
    keyboard.append([
        InlineKeyboardButton(
            text="✅ تحققت من الاشتراك",
            callback_data="check_subscription"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def send_subscription_message(update, unsubscribed_channels: list):
    """
    يرسل رسالة تطلب من المستخدم الاشتراك في القنوات.
    """
    channels_list = "\n".join([
        f"• [{ch['name']}]({ch['url']})"
        for ch in unsubscribed_channels
    ])
    
    message_text = (
        "⚠️ *يجب الاشتراك في القنوات التالية أولاً:*\n\n"
        f"{channels_list}\n\n"
        "بعد الاشتراك، اضغط على زر *تحققت من الاشتراك* 👇"
    )
    
    keyboard = get_subscription_keyboard(unsubscribed_channels)
    
    if update.callback_query:
        await update.callback_query.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
