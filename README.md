# Instagram Media Downloader Telegram Bot

A production-grade Telegram bot that downloads public Instagram content (Reels, Videos, Photos, Carousels) in the highest available quality and sends them as files (original quality, no recompression).

## Features

- 🎯 **Auto-detection** – recognizes single photos, videos, and carousels.
- 🚀 **High quality** – downloads best video+audio stream or highest‑resolution image.
- 📁 **Original files** – media is sent as Telegram documents, preserving original quality.
- 📊 **User statistics** – per‑user download count, daily limits, premium subscriptions.
- 🛡️ **Rate limiting** – prevents spam and abuse.
- 👑 **Admin panel** – broadcast, ban/unban, manage premium, maintenance mode.
- ⚡ **Concurrent downloads** – powered by asyncio.
- 🧹 **Auto cleanup** – temporary files are deleted after upload.
- 📦 **SQLite database** – persistent user stats and premium flags.
- 🔧 **Configurable via `.env`** – tokens, limits, cookies file.

## Prerequisites

- Python 3.12 or newer
- `ffmpeg` (required by yt‑dlp for merging video+audio; available on Linux, Termux, etc.)
- Telegram Bot Token (obtain from [@BotFather](https://t.me/BotFather))

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/instagram_bot.git
cd instagram_bot
