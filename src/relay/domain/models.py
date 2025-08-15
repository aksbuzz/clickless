from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class OutboxMessage:
    id: str
    destination: str
    payload: str 
    publish_at: Optional[datetime] = None
