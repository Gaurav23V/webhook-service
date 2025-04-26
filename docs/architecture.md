# Architecture & Technology Rationale

1. Framework: FastAPI  
   - Async-first design for high throughput.  
   - Automatic schema generation & interactive docs.  

2. Database: PostgreSQL  
   - Structured schema for subscriptions & logs.  
   - Support for indexing and complex queries.  
   - ACID compliance for data integrity.

3. Queue / Async: Redis + RQ  
   - Jobs persisted in Redis lists.  
   - Built-in retry/backoff support.  
   - Easy to monitor & scale workers.

4. Cache: Redis  
   - In-memory store for subscription lookups.  
   - Fast read performance, TTL support for automatic eviction.
