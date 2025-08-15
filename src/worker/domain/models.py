from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ActionResult:
  status: str
  updated_data: Dict[str, Any]