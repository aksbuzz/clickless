import os
import redis

REDIS_URL = os.getenv("REDIS_URL")
redis_client = redis.from_url(REDIS_URL)