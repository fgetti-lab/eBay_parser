# telegram.py
import httpx
from loguru import logger
from .models import EbayItem


class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram."""

    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_notification(self, item: EbayItem, channel_id: str):
        """Форматирует и отправляет сообщение в указанный канал."""
        title = self._escape_markdown(item.title)
        price = self._escape_markdown(f"{item.price} {item.currency}")

        message = (
            f"*{title}*\n\n"
            f"Цена: `{price}`\n\n"
            f"[Посмотреть на eBay]({item.url})"
        )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.api_url,
                    json={
                        "chat_id": channel_id,
                        "text": message,
                        "parse_mode": "MarkdownV2",
                        "disable_web_page_preview": False
                    }
                )
                response.raise_for_status()
                logger.debug(f"Уведомление для товара {item.item_id} успешно отправлено в канал {channel_id}.")
            except httpx.HTTPStatusError as e:
                logger.error(f"Ошибка отправки уведомления в канал {channel_id}: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при отправке в Telegram: {e}")

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Экранирует символы для Telegram MarkdownV2."""
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))