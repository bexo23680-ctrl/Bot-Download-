"""
Rate limiter using in‑memory timestamps.
"""

import time
from collections import defaultdict
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests: int = 5, window: float = 60.0):
        self.max_requests = max_requests
        self.window = window
        self._user_requests: Dict[int, List[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        # Clean old entries
        self._user_requests[user_id] = [
            ts for ts in self._user_requests[user_id] if now - ts < self.window
        ]
        if len(self._user_requests[user_id]) >= self.max_requests:
            return False
        self._user_requests[user_id].append(now)
        return True

    def clean_old(self, max_age: float = 300.0):
        """Remove entries that haven't been seen for a while (memory cleanup)."""
        now = time.time()
        for uid in list(self._user_requests.keys()):
            self._user_requests[uid] = [ts for ts in self._user_requests[uid] if now - ts < self.window]
            if not self._user_requests[uid]:
                del self._user_requests[uid]

# Create a global instance (can be configured later)
rate_limiter = RateLimiter()
