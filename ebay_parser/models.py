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
    name: str
    url: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None