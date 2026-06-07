"""
Async SQLite database for user statistics and subscription management.
"""

import aiosqlite
import os
from datetime import date
from typing import Optional, Tuple
import logging

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Connect to database and create tables. Removes corrupted database files."""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
            
            if os.path.exists(self.db_path):
                if os.path.getsize(self.db_path) == 0:
                    logger.warning(f"Removing empty database file: {self.db_path}")
                    os.remove(self.db_path)
                else:
                    try:
                        with open(self.db_path, 'rb') as f:
                            header = f.read(16)
                            if not header.startswith(b'SQLite format 3\x00'):
                                logger.warning(f"Corrupted database file, removing: {self.db_path}")
                                os.remove(self.db_path)
                    except Exception as e:
                        logger.warning(f"Cannot read database file, removing: {e}")
                        os.remove(self.db_path)
            
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._create_tables()
            logger.info(f"Database connected successfully at {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            self._conn = None
            raise

    async def close(self):
        """Safely close the database connection."""
        if self._conn:
            try:
                await self._conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database: {e}")
            finally:
                self._conn = None

    async def _create_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    total_downloads INTEGER DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_premium BOOLEAN DEFAULT 0,
                    is_banned BOOLEAN DEFAULT 0
                )
            """)
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date TEXT,
                    count INTEGER DEFAULT 0,
                    UNIQUE(user_id, date)
                )
            """)
            await self._conn.commit()
            logger.info("Database tables created/verified")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise

    async def add_or_update_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Insert or update user on interaction."""
        if not self._conn:
            logger.error("Database not connected")
            return False
            
        try:
            await self._conn.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    last_active = CURRENT_TIMESTAMP
            """, (user_id, username or "", first_name or "", last_name or ""))
            await self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[dict]:
        """Get user data by user_id."""
        if not self._conn:
            logger.error("Database not connected")
            return None
            
        try:
            async with self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return dict(zip([col[0] for col in cursor.description], row))
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def is_banned(self, user_id: int) -> bool:
        """Check if user is banned."""
        user = await self.get_user(user_id)
        return user is not None and user.get("is_banned", False)

    async def is_premium(self, user_id: int) -> bool:
        """Check if user has premium status."""
        user = await self.get_user(user_id)
        return user is not None and user.get("is_premium", False)

    async def increment_downloads(self, user_id: int) -> None:
        """Increment total_downloads and today's daily count."""
        if not self._conn:
            logger.error("Database not connected")
            return
            
        today = date.today().isoformat()
        try:
            await self._conn.execute("BEGIN")
            await self._conn.execute(
                "UPDATE users SET total_downloads = total_downloads + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            await self._conn.execute("""
                INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
            """, (user_id, today))
            await self._conn.commit()
        except Exception as e:
            logger.error(f"Error incrementing downloads: {e}")
            await self._conn.rollback()

    async def get_daily_count(self, user_id: int) -> int:
        """Get today's download count for user."""
        if not self._conn:
            logger.error("Database not connected")
            return 0
            
        today = date.today().isoformat()
        try:
            async with self._conn.execute(
                "SELECT count FROM daily_downloads WHERE user_id = ? AND date = ?", (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting daily count: {e}")
            return 0

    async def set_premium(self, user_id: int, status: bool) -> None:
        """Set user premium status."""
        if not self._conn:
            logger.error("Database not connected")
            return
            
        try:
            await self._conn.execute(
                "UPDATE users SET is_premium = ? WHERE user_id = ?",
                (1 if status else 0, user_id)
            )
            await self._conn.commit()
        except Exception as e:
            logger.error(f"Error setting premium: {e}")

    async def set_ban(self, user_id: int, status: bool) -> None:
        """Ban or unban user."""
        if not self._conn:
            logger.error("Database not connected")
            return
            
        try:
            await self._conn.execute(
                "UPDATE users SET is_banned = ? WHERE user_id = ?",
                (1 if status else 0, user_id)
            )
            await self._conn.commit()
        except Exception as e:
            logger.error(f"Error setting ban: {e}")

    async def get_stats(self) -> Tuple[int, int, int]:
        """Returns (total_users, premium_users, total_downloads)."""
        if not self._conn:
            logger.error("Database not connected")
            return 0, 0, 0
            
        try:
            async with self._conn.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            async with self._conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cursor:
                premium_users = (await cursor.fetchone())[0]
            async with self._conn.execute("SELECT COALESCE(SUM(total_downloads), 0) FROM users") as cursor:
                total_downloads = (await cursor.fetchone())[0]
            return total_users, premium_users, total_downloads
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return 0, 0, 0
