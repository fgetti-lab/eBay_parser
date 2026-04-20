# models.py
from typing import Optional
from pydantic import BaseModel, HttpUrl

class EbayItem(BaseModel):
    """Модель данных для одного товара с eBay."""
    item_id: str
    title: str
    price: float
    currency: str
    url: HttpUrl
    image_url: Optional[HttpUrl] = None

class TrackedLink(BaseModel):
    """Модель для отслеживаемой ссылки."""
    id: int
    user_id: int
    name: str
    url: str
    channel_id: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    pause_seconds: int = 600
    proxy: Optional[str] = None
    is_initial_scan: bool = True