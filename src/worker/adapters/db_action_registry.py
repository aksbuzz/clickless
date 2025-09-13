import psycopg2
from typing import Dict, Optional

from src.worker.domain.ports import ActionRegistryPort, ActionHandlerPort

class DbActionRegistry(ActionRegistryPort):
  def __init__(self, conn_str: str):
    self.db = psycopg2.connect(conn_str)
    self.cache = {}
    
    self.primitive_handlers = {
      "http_request": H
    }