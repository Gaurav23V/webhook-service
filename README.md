# Webhook Delivery Service

Backend service for reliable webhook ingestion & delivery.

## Technology Selection & Justification

We’ve chosen the following core technologies:

- **Framework:** FastAPI  
  • Async-first, high performance, built-in OpenAPI/Swagger docs.  
- **Database:** PostgreSQL  
  • Relational data (subscriptions), ACID guarantees, strong indexing.  
- **Queue & Async:** Redis + RQ  
  • Simple Python integration, lightweight, reliable retry support.  
- **Cache:** Redis  
  • In-memory, TTL eviction, ultra-low latency for subscription lookups.

