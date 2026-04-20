# core.py
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from loguru import logger
from typing import List, Optional, Dict


# Оставляем модель данных без изменений
class EbayItem:
    def __init__(self, item_id, title, price, currency, url, image_url):
        self.item_id = item_id
        self.title = title
        self.price = price
        self.currency = currency
        self.url = url
        self.image_url = image_url

    def __repr__(self):
        return f"EbayItem(item_id={self.item_id}, title='{self.title}', price={self.price} {self.currency})"


class SessionBlockedError(Exception):
    """Специальное исключение для обнаружения блокировки."""
    pass


class EbayParser:
    """Парсер для извлечения данных с HTML-страницы eBay."""

    async def fetch_html(self, url: str, proxy: Optional[str] = None, cookies: Optional[Dict] = None) -> Optional[str]:
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
        }
        proxies = {"http": proxy, "https": proxy} if proxy else None

        try:
            async with AsyncSession(proxies=proxies, timeout=30, impersonate="chrome124") as session:
                response = await session.get(url, headers=headers, cookies=cookies)
                response.raise_for_status()

                if "Pardon Our Interruption" in response.text:
                    raise SessionBlockedError("Обнаружена страница-заглушка от eBay. Сессия/Cookies устарели.")

                return response.text
        except SessionBlockedError:
            raise
        except Exception as e:
            logger.error(f"Не удалось загрузить страницу {url} (прокси: {proxy}): {e}")
            raise

    def parse_html(self, html: str) -> List[EbayItem]:
        soup = BeautifulSoup(html, 'lxml')
        items = []
        # Этот селектор хороший, он находит все карточки товаров
        item_elements = soup.select('li.s-item, li.s-card')

        if not item_elements:
            with open("debug_parser_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            logger.warning("Не найдено ни одного контейнера товаров. HTML-ответ сохранен в debug_parser_page.html.")
            return []

        logger.info(f"Найдено {len(item_elements)} элементов-контейнеров для товаров.")

        for el in item_elements:
            try:
                # --- ИСПРАВЛЕНИЕ 1: Селектор для ссылки ---
                # Ссылка на товар находится в заголовке карточки
                url_el = el.select_one('.su-card-container__header > a.su-link')
                if not url_el or not url_el.has_attr('href'):
                    continue  # Пропускаем, если это не карточка товара
                url = url_el['href']

                item_id_match = re.search(r'/itm/(\d+)', url)
                if not item_id_match:
                    continue
                item_id = item_id_match.group(1)

                # --- ИСПРАВЛЕНИЕ 2: Селектор для заголовка ---
                # Находим заголовок по его роли и извлекаем текст из внутреннего span
                title_el = el.select_one('div[role="heading"]')
                if not title_el:
                    continue

                # Удаляем лишние элементы, такие как "New Listing", если они есть
                new_listing_span = title_el.select_one('span.s-card__new-listing')
                if new_listing_span:
                    new_listing_span.decompose()  # Удаляем узел из дерева

                title = title_el.text.strip()
                if not title or title.lower() in ('shop on ebay',):
                    continue

                # --- Цена: этот блок работал хорошо, оставляем без изменений ---
                price_el = el.select_one('.s-item__price, .s-card__price')
                price_text = price_el.text.strip() if price_el else "0"

                if 'to' in price_text or 'до' in price_text.lower():
                    price_text = re.split(r'to|до', price_text, flags=re.IGNORECASE)[0].strip()

                price_cleaned = re.sub(r'[^\d,.]', '', price_text).replace(',', '.')
                price = float(price_cleaned) if price_cleaned else 0.0
                currency = re.sub(r'[\d.,\s]', '', price_text) or '$'

                # --- ИСПРАВЛЕНИЕ 3: Селектор для изображения ---
                # Класс находится на самом теге <img>, ищем также в data-defer-load
                image_el = el.select_one('img.s-card__image')
                image_url = None
                if image_el:
                    image_url = image_el.get('data-defer-load') or image_el.get('src')

                items.append(EbayItem(item_id=item_id, title=title, price=price, currency=currency, url=url,
                                      image_url=image_url))
            except Exception as e:
                logger.warning(f"Не удалось распарсить один из товаров: {e}")

        logger.info(f"Успешно обработано {len(items)} товаров.")
        return items
