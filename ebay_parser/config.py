import tomli as tomllib

from pydantic import BaseModel

class TelegramConfig(BaseModel):
    bot_token: str
    channel_id: str

class ParserConfig(BaseModel):
    pause_general: int
    pause_between_links: int

class AppConfig(BaseModel):
    telegram: TelegramConfig
    parser: ParserConfig

def load_config(path: str = "config.toml") -> AppConfig:
    """Загружает конфигурацию из TOML файла."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return AppConfig(**data)

# Загружаем конфигурацию при импорте модуля
config = load_config()