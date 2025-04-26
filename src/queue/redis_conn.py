import os
from dotenv import load_dotenv
import redis
from rq import Queue

# Load REDIS_URL from .env
load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Redis connection & RQ queue for delivery jobs
redis_conn = redis.from_url(REDIS_URL)
delivery_queue = Queue("deliveries", connection=redis_conn)