# eBay Parser Bot

Telegram-бот для мониторинга eBay-ссылок с отправкой уведомлений о новых товарах в выбранный канал.

## Что делает проект

- Хранит список отслеживаемых ссылок в SQLite.
- Периодически парсит страницы eBay.
- Фильтрует результаты по цене.
- Поддерживает ротацию прокси.
- Отправляет новые товары в Telegram-канал.
- Использует Playwright для обновления cookies при блокировках.

## Стек

- Python 3.10+
- python-telegram-bot
- BeautifulSoup + lxml
- curl_cffi
- Playwright
- SQLite

## Структура

- `main.py` - точка входа
- `ebay_parser/bot.py` - Telegram-логика и главный цикл мониторинга
- `ebay_parser/core.py` - загрузка и парсинг HTML eBay
- `ebay_parser/db_service.py` - работа с SQLite
- `ebay_parser/playwright_service.py` - получение cookies через браузер
- `ebay_parser/telegram.py` - отправка уведомлений в Telegram
- `config.toml` - конфигурация запуска
- `config.example.toml` - пример конфигурации

## Быстрый старт

1. Клонируй репозиторий:
```bash
git clone git@github.com:fgetti-lab/eBay_parser.git
cd eBay_parser
```

2. Создай виртуальное окружение и установи зависимости:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

3. Настрой конфиг:
```bash
cp config.example.toml config.toml
```
Заполни `telegram.bot_token` в `config.toml`.

4. Запусти бота:
```bash
python main.py
```

## Как пользоваться ботом

1. Запусти `/start`.
2. Нажми `Добавить ссылку`.
3. Отправь ссылку поиска eBay.
4. Укажи имя ссылки.
5. Перешли боту сообщение из канала, где бот назначен администратором.
6. Настрой фильтры/паузу/прокси в меню управления ссылкой.
