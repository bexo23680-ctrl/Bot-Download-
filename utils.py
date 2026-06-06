"""
Utility functions.
"""

import re

def is_valid_instagram_url(text: str) -> bool:
    """Check if the given text is a public Instagram URL."""
    pattern = r'https?://(www\.)?instagram\.com/(p|reel|tv)/[a-zA-Z0-9_-]+/?'
    return bool(re.match(pattern, text.strip()))

def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)
