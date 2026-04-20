import sqlite3
from loguru import logger
from typing import List, Optional
from .models import TrackedLink

class DBHandler:
    """Класс для работы с базой данных SQLite."""
    def __init__(self, db_name="parser_data.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name)
        self.create_tables()

    def create_tables(self):
        """Создает таблицы, если они не существуют."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                min_price REAL,
                max_price REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS viewed_items (
                item_id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def add_link(self, name: str, url: str) -> bool:
        """Добавляет новую ссылку для отслеживания."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO tracked_links (name, url) VALUES (?, ?)", (name, url))
            self.conn.commit()
            logger.info(f"Ссылка '{name}' добавлена в базу данных.")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Ссылка с именем '{name}' уже существует.")
            return False

    def get_all_links(self) -> List[TrackedLink]:
        """Возвращает все отслеживаемые ссылки."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, url, min_price, max_price FROM tracked_links")
        rows = cursor.fetchall()
        return [TrackedLink(id=r[0], name=r[1], url=r[2], min_price=r[3], max_price=r[4]) for r in rows]

    def delete_link(self, name: str) -> bool:
        """Удаляет ссылку по ее названию."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tracked_links WHERE name = ?", (name,))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Ссылка '{name}' удалена.")
            return True
        logger.warning(f"Ссылка с именем '{name}' не найдена.")
        return False

    def set_filters(self, name: str, min_price: Optional[float], max_price: Optional[float]) -> bool:
        """Устанавливает фильтры для ссылки."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE tracked_links SET min_price = ?, max_price = ? WHERE name = ?",
            (min_price, max_price, name)
        )
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Фильтры для '{name}' обновлены.")
            return True
        logger.warning(f"Не удалось обновить фильтры для '{name}'. Ссылка не найдена.")
        return False

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