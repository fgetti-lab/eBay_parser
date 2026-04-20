# bot.py
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from loguru import logger
import re

from .config import config
from .db_service import DBHandler
from .telegram import TelegramNotifier
from .core import EbayParser, SessionBlockedError
from .playwright_service import get_ebay_cookies

# --- Инициализация компонентов ---
db = DBHandler()
notifier = TelegramNotifier(token=config.telegram.bot_token)
parser = EbayParser()

# --- Глобальные переменные состояния ---
proxy_counters = {}
GLOBAL_COOKIES = {}
is_regenerating_cookies = asyncio.Lock()

# --- Состояния для диалогов ---
(ADD_LINK_URL, ADD_LINK_NAME, ADD_LINK_CHANNEL,
 SET_FILTER_PRICE, SET_PAUSE, SET_PROXY,
 DELETE_LINK_CONFIRM) = range(7)


# --- Клавиатуры ---
def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ссылку", callback_data="add_link")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="list_links")],
    ])


def build_links_menu(links):
    keyboard = [[InlineKeyboardButton(f"⚙️ {link.name}", callback_data=f"manage_{link.id}")] for link in links]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="start")])
    return InlineKeyboardMarkup(keyboard)


def build_manage_link_menu(link_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Установить фильтр цены", callback_data=f"set_filter_{link_id}")],
        [InlineKeyboardButton("⏱️ Установить паузу", callback_data=f"set_pause_{link_id}")],
        [InlineKeyboardButton("🌐 Установить прокси", callback_data=f"set_proxy_{link_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{link_id}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="list_links")],
    ])


# --- ОБЩИЕ ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    text = "Привет! Я бот для мониторинга eBay. Выберите действие:"
    reply_markup = build_main_menu()
    if query:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data:
        context.user_data.clear()

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Действие отменено.", reply_markup=build_main_menu())
    else:
        await update.message.reply_text("Действие отменено.", reply_markup=build_main_menu())
    return ConversationHandler.END


# --- ПРОСМОТР И УПРАВЛЕНИЕ ССЫЛКАМИ ---
async def list_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    links = db.get_all_links()
    text = "Ваши отслеживаемые ссылки:" if links else "У вас нет отслеживаемых ссылок."
    reply_markup = build_links_menu(links) if links else InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Назад", callback_data="start")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup)


async def manage_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    link_id = int(query.data.split('_')[1])
    link = db.get_link_by_id(link_id)
    if not link:
        await query.edit_message_text("Ошибка: ссылка не найдена.", reply_markup=build_main_menu())
        return

    filters_info = []
    if link.min_price is not None: filters_info.append(f"от {link.min_price}")
    if link.max_price is not None: filters_info.append(f"до {link.max_price}")
    filter_str = f"Фильтр цены: {TelegramNotifier._escape_markdown(', '.join(filters_info) or 'не задан')}"
    pause_str = f"Пауза: {link.pause_seconds} сек."

    proxy_count = len(link.proxy.split(',')) if link.proxy else 0
    proxy_str = f"Прокси: {proxy_count} шт."

    text = f"Управление ссылкой *{TelegramNotifier._escape_markdown(link.name)}*\n\n`{filter_str}`\n`{pause_str}`\n`{proxy_str}`"
    await query.edit_message_text(text=text, reply_markup=build_manage_link_menu(link_id), parse_mode='MarkdownV2')


# --- ДИАЛОГИ ---
async def add_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Шаг 1/3: Отправьте мне ссылку на страницу поиска eBay:",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("Отмена", callback_data="cancel_conv")]]))
    return ADD_LINK_URL


async def add_link_get_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['url'] = update.message.text
    await update.message.reply_text("Шаг 2/3: Отлично! Теперь придумайте короткое название для этой ссылки:",
                                    reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton("Отмена", callback_data="cancel_conv")]]))
    return ADD_LINK_NAME


async def add_link_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    text = (
        "Шаг 3/3: Супер!\n\n"
        "Теперь **создайте публичный или частный канал** и **добавьте меня туда как администратора**.\n\n"
        "После этого **перешлите мне любое сообщение из этого канала**."
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("Отмена", callback_data="cancel_conv")]]))
    return ADD_LINK_CHANNEL


async def add_link_get_channel_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.forward_origin:
        await update.message.reply_text(
            "Это не пересланное сообщение. Пожалуйста, именно **перешлите** сообщение из вашего канала.",
            parse_mode='Markdown')
        return ADD_LINK_CHANNEL
    if update.message.forward_origin.type != 'channel':
        await update.message.reply_text(
            "Пожалуйста, перешлите сообщение именно из **канала**, а не из личного чата или группы.")
        return ADD_LINK_CHANNEL

    channel_id = str(update.message.forward_origin.chat.id)
    user_id = update.message.from_user.id
    name = context.user_data['name']
    url = context.user_data['url']

    if db.add_link(user_id, name, url, channel_id):
        await update.message.reply_text(f"✅ Готово! Ссылка '{name}' добавлена.", reply_markup=build_main_menu())
        try:
            test_message = f"✅ Этот канал успешно привязан для отслеживания ссылки '{name}'."
            await context.bot.send_message(chat_id=channel_id, text=test_message)
            logger.info(f"Тестовое сообщение успешно отправлено в канал {channel_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить тестовое сообщение в канал {channel_id}: {e}")
            await update.message.reply_text(
                f"⚠️ Не удалось отправить тестовое сообщение в канал. Убедитесь, что я добавлен туда как администратор.")
    else:
        await update.message.reply_text(f"⚠️ Ссылка с именем '{name}' уже существует.", reply_markup=build_main_menu())

    context.user_data.clear()
    return ConversationHandler.END


async def delete_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    link_id = int(query.data.split('_')[1])
    link = db.get_link_by_id(link_id)
    if not link:
        await query.edit_message_text("Ошибка: ссылка не найдена.", reply_markup=build_main_menu())
        return ConversationHandler.END

    context.user_data['link_id_to_delete'] = link_id
    text = f"Вы уверены, что хотите удалить ссылку '{link.name}'?"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Да, удалить", callback_data="delete_confirm")],
        [InlineKeyboardButton("Нет, отмена", callback_data=f"manage_{link_id}")]
    ]))
    return DELETE_LINK_CONFIRM


async def delete_link_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    link_id = context.user_data.get('link_id_to_delete')
    if link_id:
        link = db.get_link_by_id(link_id)
        if link and link.id in proxy_counters:
            del proxy_counters[link.id]
        db.delete_link(link_id)
        await query.edit_message_text("🗑️ Ссылка удалена.", reply_markup=build_main_menu())
    else:
        await query.edit_message_text("Ошибка при удалении.", reply_markup=build_main_menu())
    context.user_data.clear()
    return ConversationHandler.END


async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, link_id_str = query.data.rsplit('_', 1)
    link_id = int(link_id_str)
    context.user_data['link_id'] = link_id

    prompts = {
        'set_filter': (
        "Отправьте минимальную и максимальную цену через пробел \\(например, `100 500`\\)\\.\nЧтобы убрать фильтр, отправьте `0`\\.",
        SET_FILTER_PRICE),
        'set_pause': (
        "Отправьте паузу между проверками в секундах \\(например, `60`\\)\\.\n*Чем меньше пауза, тем выше нагрузка и шанс блокировки без пула прокси\\!*",
        SET_PAUSE),
        'set_proxy': (
        "Отправьте один или несколько прокси\\. Каждый прокси с новой строки\\.\nФормат: `login:pass@ip:port` или `ip:port`\n\nОтправьте `0` чтобы убрать все прокси\\.",
        SET_PROXY)
    }
    prompt_text, next_state = prompts.get(action, (None, None))
    if not prompt_text: return ConversationHandler.END

    await query.edit_message_text(prompt_text, parse_mode='MarkdownV2', reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("Отмена", callback_data="cancel_conv")]]))
    return next_state


async def set_filter_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_id = context.user_data['link_id']
    try:
        prices = update.message.text.split()
        if len(prices) == 1 and prices[0] == '0':
            min_p, max_p = None, None
        elif len(prices) == 2:
            min_p, max_p = float(prices[0]), float(prices[1])
        else:
            raise ValueError("Invalid format")
    except (ValueError, IndexError):
        await update.message.reply_text("Неверный формат. Отправьте две цифры (100 500) или 0.")
        return SET_FILTER_PRICE

    db.set_filters(link_id, min_p, max_p)
    await update.message.reply_text("✅ Фильтры цены обновлены.", reply_markup=build_main_menu())
    context.user_data.clear()
    return ConversationHandler.END


async def set_pause_get_seconds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_id = context.user_data['link_id']
    try:
        pause = int(update.message.text)
        if pause < 5:
            await update.message.reply_text("Пауза должна быть не менее 5 секунд.")
            return SET_PAUSE
    except ValueError:
        await update.message.reply_text("Неверный формат. Отправьте целое число.")
        return SET_PAUSE
    db.set_pause(link_id, pause)
    await update.message.reply_text(f"✅ Пауза обновлена на {pause} секунд.", reply_markup=build_main_menu())
    context.user_data.clear()
    return ConversationHandler.END


async def set_proxy_get_string(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_id = context.user_data['link_id']
    if link_id in proxy_counters:
        del proxy_counters[link_id]

    proxy_input = update.message.text.strip()
    if proxy_input == '0':
        db.set_proxy(link_id, None)
        await update.message.reply_text("✅ Все прокси убраны.", reply_markup=build_main_menu())
    else:
        proxies = [p.strip() for p in proxy_input.splitlines() if p.strip()]
        valid_proxies = []
        for proxy in proxies:
            if "socks5" in proxy.lower() and not proxy.startswith("socks5://"):
                valid_proxies.append("socks5://" + re.sub(r'socks5://', '', proxy, flags=re.IGNORECASE))
            elif "http" not in proxy.lower() and "socks" not in proxy.lower():
                valid_proxies.append("http://" + proxy)
            else:
                valid_proxies.append(proxy)
        proxy_to_save = ",".join(valid_proxies)
        db.set_proxy(link_id, proxy_to_save)
        await update.message.reply_text(f"✅ Добавлено/обновлено {len(valid_proxies)} прокси.",
                                        reply_markup=build_main_menu())

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cancel(update, context)


async def regenerate_global_cookies():
    global GLOBAL_COOKIES

    async with is_regenerating_cookies:
        logger.info("Начинаю процедуру обновления cookies...")

        links = db.get_all_links()
        proxy_to_use = None
        if links:
            for link in links:
                if link.proxy:
                    proxy_to_use = link.proxy.split(',')[0].strip()
                    logger.info(f"Для обновления cookies будет использован прокси: {proxy_to_use}")
                    break

        new_cookies = await get_ebay_cookies(proxy=proxy_to_use)
        if new_cookies:
            GLOBAL_COOKIES = new_cookies
        else:
            logger.error(
                "Не удалось обновить cookies. Парсинг может быть нестабильным. Следующая попытка через 5 минут.")
            await asyncio.sleep(300)


# --- ДИАГНОСТИЧЕСКАЯ ВЕРСИЯ ГЛАВНОГО ЦИКЛА ПАРСЕРА ---
async def main_parser_loop(application: Application):
    logger.info("--- ЗАПУСК ДИАГНОСТИЧЕСКОГО РЕЖИМА ПАРСЕРА ---")

    diagnostic_run_complete = False

    while True:
        try:
            tracked_links = db.get_all_links()
            if not tracked_links:
                await asyncio.sleep(60)
                continue

            for link in tracked_links:
                selected_proxy = None
                if link.proxy:
                    proxy_list = [p.strip() for p in link.proxy.split(',')]
                    if proxy_list:
                        current_index = proxy_counters.get(link.id, 0)
                        selected_proxy = proxy_list[current_index]
                        proxy_counters[link.id] = (current_index + 1) % len(proxy_list)

                logger.info(f"Проверяю '{link.name}' (прокси: {selected_proxy or 'None'})...")

                try:
                    html = await parser.fetch_html(link.url, proxy=selected_proxy, cookies=GLOBAL_COOKIES)

                    if html and not diagnostic_run_complete:
                        with open("debug_parser_page.html", "w", encoding="utf-8") as f:
                            f.write(html)
                        logger.success(
                            "ДИАГНОСТИКА: HTML-страница, которую видит парсер, УСПЕШНО СОХРАНЕНА в 'debug_parser_page.html'")
                        diagnostic_run_complete = True

                    if not html: raise ConnectionError("HTML content is empty")

                    items = parser.parse_html(html)

                    if link.is_initial_scan:
                        for item in items: db.add_viewed_item(item.item_id)
                        if db.mark_as_scanned(link.id): logger.info(
                            f"Инициализация ссылки '{link.name}': сохранено {len(items)} товаров.")
                    else:
                        new_items_count = 0
                        for item in items:
                            if db.is_item_viewed(item.item_id): continue
                            if (link.min_price is not None and item.price < link.min_price) or \
                                    (link.max_price is not None and item.price > link.max_price): continue
                            await notifier.send_notification(item, link.channel_id)
                            db.add_viewed_item(item.item_id)
                            new_items_count += 1
                            await asyncio.sleep(1)
                        if new_items_count > 0: logger.info(
                            f"Найдено новых товаров для '{link.name}': {new_items_count}.")

                except SessionBlockedError as e:
                    logger.warning(f"Блокировка сессии при проверке '{link.name}': {e}")
                    await application.bot.send_message(chat_id=link.user_id,
                                                       text="⚠️ Обнаружена блокировка eBay. Запускаю автоматическое обновление сессии...")
                    await regenerate_global_cookies()
                    diagnostic_run_complete = False  # Сбрасываем флаг, чтобы сохранить HTML после обновления cookies
                    break

                except Exception as e:
                    logger.error(f"Ошибка при обработке '{link.name}': {e}")
                    escaped_error = TelegramNotifier._escape_markdown(str(e))
                    escaped_name = TelegramNotifier._escape_markdown(link.name)
                    error_message = f"‼️ *Ошибка при проверке ссылки '{escaped_name}'*\n\n`{escaped_error}`\n\nБот продолжит попытки\\."
                    await application.bot.send_message(chat_id=link.user_id, text=error_message,
                                                       parse_mode='MarkdownV2')

                await asyncio.sleep(link.pause_seconds)
        except Exception as e:
            logger.critical(f"Критическая ошибка в основном цикле парсера: {e}")
            await asyncio.sleep(60)


async def post_init(application: Application):
    await application.bot.set_my_commands([('start', '🚀 Запустить/перезапустить бота')])


async def run_app():
    await regenerate_global_cookies()
    if not GLOBAL_COOKIES:
        logger.critical("Не удалось получить первичные cookies. Бот не может быть запущен.")
        return

    application = Application.builder().token(config.telegram.bot_token).post_init(post_init).build()

    conv_fallbacks = [CallbackQueryHandler(cancel_conversation, pattern='^cancel_conv$'),
                      CommandHandler('cancel', cancel)]

    add_link_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_link_start, pattern='^add_link$')],
        states={
            ADD_LINK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_link_get_url)],
            ADD_LINK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_link_get_name)],
            ADD_LINK_CHANNEL: [MessageHandler(filters.ALL & ~filters.COMMAND, add_link_get_channel_and_save)]
        },
        fallbacks=conv_fallbacks, per_message=False
    )
    delete_link_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_link_start, pattern='^delete_\\d+$')],
        states={DELETE_LINK_CONFIRM: [CallbackQueryHandler(delete_link_confirm, pattern='^delete_confirm$')]},
        fallbacks=[CallbackQueryHandler(manage_link, pattern='^manage_\\d+$')], per_message=False
    )
    settings_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_start, pattern='^(set_filter|set_pause|set_proxy)_\\d+$')],
        states={
            SET_FILTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_filter_get_price)],
            SET_PAUSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_pause_get_seconds)],
            SET_PROXY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_proxy_get_string)]
        },
        fallbacks=conv_fallbacks, per_message=False
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(start, pattern='^start$'))
    application.add_handler(CallbackQueryHandler(list_links, pattern='^list_links$'))
    application.add_handler(CallbackQueryHandler(manage_link, pattern='^manage_\\d+$'))
    application.add_handler(add_link_handler)
    application.add_handler(delete_link_handler)
    application.add_handler(settings_handler)

    async with application:
        logger.info("Запуск Telegram-бота...")
        await application.start()
        await application.updater.start_polling()
        parser_task = asyncio.create_task(main_parser_loop(application))
        await asyncio.Event().wait()
        parser_task.cancel()
        await application.updater.stop()
        await application.stop()
        logger.info("Приложение корректно остановлено.")