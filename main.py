import asyncio
import os
from loguru import logger
from ebay_parser.bot import run_app

if __name__ == '__main__':
    # Создаем папку для логов, если ее нет
    os.makedirs("logs", exist_ok=True)

    logger.add("logs/app.log", rotation="5 MB", retention="5 days", level="INFO")

    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("Приложение остановлено вручную.")