# db_service.py
import sqlite3
from loguru import logger
from typing import List, Optional
from .models import TrackedLink

class DBHandler:
    """Класс для работы с базой данных SQLite."""
    def __init__(self, db_name="parser_data.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        """Создает таблицы, если они не существуют."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                min_price REAL,
                max_price REAL,
                pause_seconds INTEGER DEFAULT 600,
                proxy TEXT,
                is_initial_scan BOOLEAN DEFAULT 1 
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS viewed_items (
                item_id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def add_link(self, user_id: int, name: str, url: str, channel_id: str) -> bool:
        """Добавляет новую ссылку для отслеживания."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO tracked_links (user_id, name, url, channel_id) VALUES (?, ?, ?, ?)",
                (user_id, name, url, channel_id)
            )
            self.conn.commit()
            logger.info(f"Ссылка '{name}' от пользователя {user_id} добавлена в базу данных.")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Ссылка с именем '{name}' уже существует.")
            return False

    def get_all_links(self) -> List[TrackedLink]:
        """Возвращает все отслеживаемые ссылки."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, user_id, name, url, channel_id, min_price, max_price, pause_seconds, proxy, is_initial_scan FROM tracked_links")
        rows = cursor.fetchall()
        return [
            TrackedLink(
                id=r[0], user_id=r[1], name=r[2], url=r[3], channel_id=r[4],
                min_price=r[5], max_price=r[6], pause_seconds=r[7], proxy=r[8],
                is_initial_scan=bool(r[9])
            ) for r in rows
        ]

    def get_link_by_id(self, link_id: int) -> Optional[TrackedLink]:
        """Возвращает одну ссылку по ее ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, user_id, name, url, channel_id, min_price, max_price, pause_seconds, proxy, is_initial_scan FROM tracked_links WHERE id = ?", (link_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return TrackedLink(
            id=row[0], user_id=row[1], name=row[2], url=row[3], channel_id=row[4],
            min_price=row[5], max_price=row[6], pause_seconds=row[7], proxy=row[8],
            is_initial_scan=bool(row[9])
        )

    def delete_link(self, link_id: int) -> bool:
        """Удаляет ссылку по ее ID."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tracked_links WHERE id = ?", (link_id,))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Ссылка с ID {link_id} удалена.")
            return True
        logger.warning(f"Ссылка с ID {link_id} не найдена.")
        return False

    def set_filters(self, link_id: int, min_price: Optional[float], max_price: Optional[float]) -> bool:
        """Устанавливает фильтры для ссылки."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tracked_links SET min_price = ?, max_price = ? WHERE id = ?", (min_price, max_price, link_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def set_pause(self, link_id: int, pause_seconds: int) -> bool:
        """Устанавливает индивидуальную паузу для ссылки."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tracked_links SET pause_seconds = ? WHERE id = ?", (pause_seconds, link_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def set_proxy(self, link_id: int, proxy: Optional[str]) -> bool:
        """Устанавливает прокси для ссылки."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tracked_links SET proxy = ? WHERE id = ?", (proxy, link_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def mark_as_scanned(self, link_id: int) -> bool:
        """Помечает, что первоначальное сканирование ссылки завершено."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tracked_links SET is_initial_scan = 0 WHERE id = ?", (link_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def is_item_viewed(self, item_id: str) -> bool:
        """Проверяет, был ли товар уже просмотрен."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM viewed_items WHERE item_id = ?", (item_id,))
        return cursor.fetchone() is not None

    def add_viewed_item(self, item_id: str):
        """Добавляет ID товара в базу просмотренных."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO viewed_items (item_id) VALUES (?)", (item_id,))
        self.conn.commit()