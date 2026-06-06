"""
Utility functions.
"""

import re

def is_valid_instagram_url(text: str) -> bool:
    """Check if the given text is a public Instagram URL."""
    pattern = r'https?://(www\.)?instagram\.com/(p|reel|tv)/[a-zA-Z0-9_-]+/?'
    return bool(re.match(pattern, text.strip()))
