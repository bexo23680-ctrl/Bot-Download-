"""
نظام الاشتراك الإجباري - يجب على المستخدم الاشتراك في القنوات المحددة.
"""

import logging
from typing import Optional, Tuple, List
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# قائمة القنوات الإجبارية
REQUIRED_CHANNELS = [
    {
        'username': '@BEXO50',
        'chat_id': '@BEXO50',
        'name': 'قناة BEXO50',
        'url': 'https://t.me/BEXO50',
    },
    # يمكنك إضافة قنوات أخرى هنا
    # {
    #     'username': '@CHANNEL2',
    #     'chat_id': '@CHANNEL2',
    #     'name': 'القناة الثانية',
    #     'url': 'https://t.me/CHANNEL2',
    # },
]

async def check_user_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[dict]]:
    """
    يتحقق من اشتراك المستخدم في جميع القنوات المطلوبة.
    
    Args:
        bot: تيليجرام بوت
        user_id: معرف المستخدم
        
    Returns:
        (is_subscribed, list_of_unsubscribed_channels)
    """
    unsubscribed = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(
                chat_id=channel['chat_id'],
                user_id=user_id
            )
            
            allowed_statuses = ['creator', 'administrator', 'member']
            
            if member.status not in allowed_statuses:
                unsubscribed.append(channel)
                logger.info(f"User {user_id} not subscribed to {channel['username']} (status: {member.status})")
            
        except TelegramError as e:
            logger.error(f"Error checking subscription for {channel['username']}: {e}")
            unsubscribed.append(channel)
    
    is_subscribed = len(unsubscribed) == 0
    return is_subscribed, unsubscribed


def get_subscription_keyboard(unsubscribed_channels: List[dict]) -> InlineKeyboardMarkup:
    """
    ينشئ أزرار للاشتراك في القنوات غير المشترك فيها.
    
    Args:
        unsubscribed_channels: القنوات غير المشترك فيها
        
    Returns:
        InlineKeyboardMarkup
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
    
    Args:
        update: تحديث تيليجرام
        unsubscribed_channels: القنوات غير المشترك فيها
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
    
    if hasattr(update, 'callback_query') and update.callback_query:
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
