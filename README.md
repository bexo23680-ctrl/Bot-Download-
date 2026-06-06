# Instagram Media Downloader Telegram Bot

A production-grade Telegram bot that downloads public Instagram content with mandatory channel subscription.

## Features

- 🎯 Auto-detection of Reels, Videos, Photos, Carousels
- 🔒 Mandatory channel subscription (@BEXO50)
- 🚀 High quality downloads
- 📁 Original files (no recompression)
- 📊 User statistics & limits
- 🛡️ Rate limiting & anti-spam
- 👑 Admin panel
- ⚡ Async concurrent downloads
- 🧹 Auto cleanup

## Quick Deploy on Railway

1. Fork this repository
2. Connect to Railway
3. Set environment variables:
   - `BOT_TOKEN`
   - `ADMINS`
4. Deploy

## Required Channels

Users must subscribe to:
- [@BEXO50](https://t.me/BEXO50)

Edit `subscription.py` to add/remove channels.

## Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Admin panel |
| `/broadcast <msg>` | Message all users |
| `/ban <user_id>` | Ban user |
| `/unban <user_id>` | Unban user |
| `/premium <user_id>` | Grant premium |
| `/unpremium <user_id>` | Remove premium |
| `/maintenance on/off` | Toggle maintenance |
| `/channels` | List required channels |

## Requirements

- Python 3.12+
- ffmpeg
- Telegram Bot Token
