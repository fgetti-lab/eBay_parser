# playwright_service.py
import asyncio
from typing import Optional, Dict

from loguru import logger
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async as stealth


async def get_ebay_cookies(proxy: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Запускает Playwright для получения "человеческих" cookies с eBay.
    """
    logger.info("Запуск сессии Playwright для получения cookies...")

    async with async_playwright() as p:
        browser = None
        page = None
        try:
            # ЗАПУСКАЕМ БРАУЗЕР В ВИДИМОМ РЕЖИМЕ, ЭТО САМОЕ ВАЖНОЕ
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])

            context_args = {
                "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                "viewport": {"width": 1920, "height": 1080},
            }
            if proxy:
                logger.info(f"Playwright будет использовать прокси: {proxy}")
                context_args["proxy"] = {"server": proxy}

            context = await browser.new_context(**context_args)
            page = await context.new_page()
            await stealth(page)

            main_url = "https://by.ebay.com/"
            logger.info(f"Playwright переходит на: {main_url}")
            # Устанавливаем большой таймаут, чтобы страница точно успела загрузиться
            await page.goto(main_url, timeout=120000, wait_until="domcontentloaded")

            # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: НЕ ЖДЕМ ЭЛЕМЕНТ, А ПРОСТО ДЕЛАЕМ ПАУЗУ ---
            logger.info("Страница загружена. Ожидание 15 секунд для стабилизации и сбора cookies...")
            await asyncio.sleep(15)

            # Если после паузы мы все еще на странице верификации, сообщаем об этом
            if "captcha" in page.url or "verify" in page.url:
                logger.error("Обнаружена страница верификации (капча). Невозможно получить cookies.")
                await page.screenshot(path="debug_captcha.png")
                logger.info("Скриншот капчи сохранен в 'debug_captcha.png'")
                raise Exception("Captcha/Verification page detected")

            # Собираем cookies, какие есть
            cookies_list = await context.cookies()
            cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies_list}

            await browser.close()

            if cookies_dict:
                logger.success("Успешно получены новые cookies через Playwright.")
                return cookies_dict
            else:
                logger.warning("Playwright завершил работу, но cookies не были получены.")
                return None

        except Exception as e:
            logger.error(f"Ошибка во время сессии Playwright: {e}")
            if page:
                try:
                    await page.screenshot(path="debug_playwright.png", full_page=True)
                    logger.info("Сделан скриншот страницы 'debug_playwright.png' для анализа ошибки.")
                except Exception as screenshot_error:
                    logger.error(f"Не удалось сделать скриншот: {screenshot_error}")

            if browser and browser.is_connected():
                await browser.close()
            return None