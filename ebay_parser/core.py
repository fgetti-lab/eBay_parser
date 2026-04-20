import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from loguru import logger
from typing import List, Optional
from .models import EbayItem


class EbayParser:
    """Парсер для извлечения данных с HTML-страницы eBay."""

    async def fetch_html(self, url: str) -> Optional[str]:
        """Загружает HTML-код страницы."""
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'accept-language': 'en-US,en;q=0.9',
        }
        try:
            async with AsyncSession() as session:
                response = await session.get(url, headers=headers, impersonate="chrome120", timeout=20)
                response.raise_for_status()
                logger.debug(f"Страница {url} успешно загружена, статус: {response.status_code}")
                return response.text
        except Exception as e:
            logger.error(f"Не удалось загрузить страницу {url}: {e}")
            return None

    def parse_html(self, html: str) -> List[EbayItem]:
        """Извлекает данные о товарах со страницы."""
        soup = BeautifulSoup(html, 'lxml')
        items = []
        item_elements = soup.select('li.s-card.s-card--horizontal')
        logger.info(f"Найдено {len(item_elements)} элементов-контейнеров для товаров.")

        for el in item_elements:
            try:
                title_el = el.select_one('.s-card__title')
                if not title_el: continue

                new_listing_span = title_el.select_one('span.s-card__new-listing')
                if new_listing_span:
                    new_listing_span.extract()
                title = title_el.text.strip()

                price_el = el.select_one('span.s-card__price')
                price_text = price_el.text.strip() if price_el else "0"

                if 'to' in price_text:
                    price_text = price_text.split('to')[0].strip()

                price_cleaned = re.sub(r'[^\d.]', '', price_text)
                price = float(price_cleaned) if price_cleaned else 0.0
                currency = ''.join(filter(str.isalpha, price_text.replace("US", ""))) or "$"

                url_el = el.select_one('a.s-card__link') or el.select_one('a.su-link')
                url = url_el['href'] if url_el else "N/A"

                item_id_match = re.search(r'/itm/(\d+)', url)
                if not item_id_match: continue
                item_id = item_id_match.group(1)

                image_el = el.select_one('img.s-card__image')
                image_url = image_el['src'] if image_el else None

                items.append(EbayItem(
                    item_id=item_id,
                    title=title,
                    price=price,
                    currency=currency,
                    url=url,
                    image_url=image_url
                ))
            except Exception as e:
                logger.warning(f"Не удалось распарсить один из товаров: {e}")

        logger.info(f"Успешно обработано {len(items)} товаров.")
        return items