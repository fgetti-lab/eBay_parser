import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from loguru import logger

from .config import config
from .db_service import DBHandler
from .telegram import TelegramNotifier
from .core import EbayParser

# Инициализация всех компонентов
db = DBHandler()
notifier = TelegramNotifier(token=config.telegram.bot_token, channel_id=config.telegram.channel_id)
parser = EbayParser()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и справку по командам."""
    help_text = (
        "Привет! Я бот для мониторинга eBay.\n\n"
        "**Доступные команды:**\n"
        "`/add <ссылка> <название>` - Добавить ссылку для отслеживания.\n"
        "`/list` - Показать все отслеживаемые ссылки.\n"
        "`/delete <название>` - Удалить ссылку.\n"
        "`/set_filter <название> min=<число> max=<число>` - Установить ценовой фильтр.\n\n"
        "**Пример добавления:**\n"
        "`/add https://www.ebay.com/sch/i.html?_nkw=iphone+15 айфоны 15`\n\n"
        "**Пример установки фильтра:**\n"
        "`/set_filter айфоны 15 min=500 max=1000`"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет новую ссылку в базу данных."""
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add <ссылка> <название>")
        return
    url, name = context.args[0], " ".join(context.args[1:])
    if db.add_link(name, url):
        await update.message.reply_text(f"✅ Ссылка '{name}' успешно добавлена.")
    else:
        await update.message.reply_text(f"⚠️ Ссылка с именем '{name}' уже существует.")


async def list_links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все отслеживаемые ссылки и их фильтры."""
    links = db.get_all_links()
    if not links:
        await update.message.reply_text("Нет отслеживаемых ссылок. Добавьте первую с помощью команды /add.")
        return

    message_parts = ["*Отслеживаемые ссылки:*\n"]
    for link in links:
        filters = []
        if link.min_price is not None:
            filters.append(f"мин. цена: {link.min_price}")
        if link.max_price is not None:
            filters.append(f"макс. цена: {link.max_price}")

        filter_str = f" _(фильтры: {', '.join(filters)})_" if filters else ""
        message_parts.append(f"- *{link.name}*{filter_str}")

    await update.message.reply_text("\n".join(message_parts), parse_mode='Markdown')


async def delete_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет ссылку из базы данных."""
    if not context.args:
        await update.message.reply_text("Использование: /delete <название>")
        return
    name = " ".join(context.args)
    if db.delete_link(name):
        await update.message.reply_text(f"🗑️ Ссылка '{name}' удалена.")
    else:
        await update.message.reply_text(f"⚠️ Ссылка с именем '{name}' не найдена.")


async def set_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает фильтры для существующей ссылки."""
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /set_filter <название> min=<число> max=<число>")
        return

    name = context.args[0]
    min_p, max_p = None, None

    for arg in context.args[1:]:
        try:
            if 'min=' in arg:
                min_p = float(arg.split('=')[1])
            if 'max=' in arg:
                max_p = float(arg.split('=')[1])
        except (ValueError, IndexError):
            await update.message.reply_text(f"⚠️ Неверный формат значения для фильтра: {arg}")
            return

    if db.set_filters(name, min_p, max_p):
        await update.message.reply_text(f"⚙️ Фильтры для '{name}' установлены.")
    else:
        await update.message.reply_text(f"⚠️ Ссылка '{name}' не найдена.")


async def main_parser_loop():
    """Основной цикл, который запускает парсинг."""
    logger.info("Запуск основного цикла парсера...")
    while True:
        try:
            tracked_links = db.get_all_links()
            if not tracked_links:
                logger.info("Нет ссылок для отслеживания. Следующая проверка через 60 секунд.")
                await asyncio.sleep(60)
                continue

            logger.info(f"Начинаю проверку {len(tracked_links)} ссылок.")

            for link in tracked_links:
                html = await parser.fetch_html(link.url)
                if not html:
                    await asyncio.sleep(config.parser.pause_between_links)
                    continue

                items = parser.parse_html(html)
                new_items_count = 0

                for item in items:
                    if db.is_item_viewed(item.item_id):
                        continue

                    if link.min_price is not None and item.price < link.min_price:
                        continue
                    if link.max_price is not None and item.price > link.max_price:
                        continue

                    await notifier.send_notification(item)
                    db.add_viewed_item(item.item_id)
                    new_items_count += 1
                    await asyncio.sleep(1)

                logger.info(f"Проверка '{link.name}' завершена. Найдено новых товаров: {new_items_count}.")
                await asyncio.sleep(config.parser.pause_between_links)

            logger.info(f"Все ссылки проверены. Пауза на {config.parser.pause_general} секунд.")
            await asyncio.sleep(config.parser.pause_general)
        except Exception as e:
            logger.error(f"Произошла ошибка в основном цикле парсера: {e}")
            await asyncio.sleep(60)


# --- ИЗМЕНЕННАЯ ФУНКЦИЯ ЗАПУСКА ---
async def run_app():
    """Главная функция для запуска бота и парсера."""
    application = Application.builder().token(config.telegram.bot_token).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_link_command))
    application.add_handler(CommandHandler("list", list_links_command))
    application.add_handler(CommandHandler("delete", delete_link_command))
    application.add_handler(CommandHandler("set_filter", set_filter_command))

    # Используем `async with` для корректного управления жизненным циклом бота
    # Это автоматически вызовет application.initialize() и application.shutdown()
    async with application:
        logger.info("Запуск Telegram-бота...")
        await application.start()
        await application.updater.start_polling()

        # Запускаем цикл парсера как фоновую задачу
        await main_parser_loop()

        # Эти строки кода больше не будут достигнуты, так как парсер работает в бесконечном цикле,
        # но `async with` гарантирует, что при остановке (например, Ctrl+C) бот корректно завершит работу.
        await application.updater.stop()
        await application.stop()