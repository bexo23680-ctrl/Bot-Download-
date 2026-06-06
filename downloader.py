"""
yt‑dlp wrapper with progress callbacks.
"""

import asyncio
import os
import uuid
import logging
from typing import Callable, List, Optional, Dict, Any

import yt_dlp

from config import COOKIES_FILE, DOWNLOAD_DIR

logger = logging.getLogger(__name__)

class Downloader:
    """Async wrapper around yt-dlp."""

    def __init__(self):
        self.cookies_file = COOKIES_FILE
        self.download_dir = DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)

    async def get_media_info(self, url: str) -> Dict[str, Any]:
        """Extract metadata without downloading."""
        loop = asyncio.get_running_loop()

        def extract():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'cookiefile': self.cookies_file,
                'noplaylist': False,  # we want to see if playlist exists
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info

        info = await loop.run_in_executor(None, extract)
        return self._parse_info(info)

    def _parse_info(self, info: dict) -> dict:
        """Determine media type and return simplified dict."""
        entries = info.get('entries')
        if entries:
            # It's a carousel (playlist)
            return {
                'type': 'carousel',
                'title': info.get('title', 'Instagram carousel'),
                'uploader': info.get('uploader', ''),
                'count': len(entries),
            }
        else:
            # Single post
            ext = info.get('ext', '')
            if ext in ('mp4', 'webm', 'mkv'):
                media_type = 'video'
            else:
                media_type = 'photo'
            return {
                'type': media_type,
                'title': info.get('title', ''),
                'uploader': info.get('uploader', ''),
                'duration': info.get('duration'),
                'format': info.get('format', ''),
            }

    async def download(
        self,
        url: str,
        progress_callback: Callable[[float, str], None],
    ) -> List[str]:
        """
        Download media and return list of file paths.
        progress_callback receives (percentage, speed_str).
        """
        loop = asyncio.get_running_loop()
        unique_id = str(uuid.uuid4())
        output_dir = os.path.join(self.download_dir, unique_id)
        os.makedirs(output_dir, exist_ok=True)
        outtmpl = os.path.join(output_dir, '%(title).100s_%(id)s.%(ext)s')

        # list to collect downloaded files
        downloaded_files: List[str] = []

        def progress_hook(d):
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0%').strip('%')
                try:
                    percent = float(percent_str)
                except ValueError:
                    percent = 0.0
                speed = d.get('_speed_str', 'N/A')
                # Schedule async callback
                asyncio.run_coroutine_threadsafe(
                    progress_callback(percent, speed), loop
                )
            elif d['status'] == 'finished':
                filepath = d.get('filename')
                if filepath:
                    downloaded_files.append(filepath)

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
            'cookiefile': self.cookies_file,
            'noplaylist': False,       # allow carousels
            'ignoreerrors': False,
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 3,
        }

        try:
            def sync_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

            await loop.run_in_executor(None, sync_download)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            # clean up partially downloaded files
            self._clean_dir(output_dir)
            raise

        # If nothing downloaded (possible error), raise
        if not downloaded_files:
            self._clean_dir(output_dir)
            raise RuntimeError("No files were downloaded")

        return downloaded_files

    def _clean_dir(self, path: str):
        """Remove directory and its contents."""
        import shutil
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
        except Exception as e:
            logger.warning(f"Failed to clean directory {path}: {e}")
