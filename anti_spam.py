"""
Rate limiter using in‑memory timestamps.
"""

import time
from collections import defaultdict
from typing import Dict, List
import logging

from config import RATE_LIMIT_MAX, RATE_LIMIT_WINDOW

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests: int = None, window: float = None):
        self.max_requests = max_requests or RATE_LIMIT_MAX
        self.window = window or RATE_LIMIT_WINDOW
        self._user_requests: Dict[int, List[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to make a request."""
        now = time.time()
        self._user_requests[user_id] = [
            ts for ts in self._user_requests[user_id] if now - ts < self.window
        ]
        if len(self._user_requests[user_id]) >= self.max_requests:
            return False
        self._user_requests[user_id].append(now)
        return True

    def clean_old(self, max_age: float = 300.0):
        """Remove entries that haven't been seen for a while."""
        now = time.time()
        for uid in list(self._user_requests.keys()):
            self._user_requests[uid] = [ts for ts in self._user_requests[uid] if now - ts < self.window]
            if not self._user_requests[uid]:
                del self._user_requests[uid]

    def get_remaining(self, user_id: int) -> int:
        """Get remaining requests for user in current window."""
        now = time.time()
        self._user_requests[user_id] = [
            ts for ts in self._user_requests[user_id] if now - ts < self.window
        ]
        return max(0, self.max_requests - len(self._user_requests[user_id]))

rate_limiter = RateLimiter()
