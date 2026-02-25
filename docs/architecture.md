User (Browser)
     │
     ▼
Next.js Frontend  ──────────────────────────────────────┐
     │                                                  │
     │ POST /chat (streaming SSE)                       │
     ▼                                                  │
FastAPI Backend                                         │
     │                                                  │
     ├── Conversation Manager (session/history)         │
     │                                                  │
     ├── User Profile Builder (extracts preferences)    │
     │                                                  │
     ├── Coffee Retrieval Engine                        │
     │        ├── PostgreSQL (your curated coffees)     │
     │        ├── pgvector semantic search              │
     │        └── Affiliate link resolver               │
     │                                                  │
     ├── LLM Orchestration Layer (Claude/OpenAI)        │
     │        ├── System prompt with coffee context     │
     │        └── Streaming response handler            │
     │                                                  │
     └── Scraper Service (async, scheduled)             │
              ├── Scrapy spiders                        │
              ├── Data normalizer                       │
              └── DB ingestion pipeline                 │

backend/
├── main.py                   # FastAPI app entry point
├── requirements.txt
├── .env
│
├── api/
│   ├── routes/
│   │   ├── chat.py           # POST /chat - main chatbot endpoint
│   │   ├── coffees.py        # GET /coffees - admin/browse endpoint
│   │   └── admin.py          # POST /coffees - add your own entries
│   └── middleware.py         # CORS, rate limiting
│
├── core/
│   ├── config.py             # env vars, settings
│   ├── database.py           # SQLAlchemy async engine + session
│   └── redis.py              # Redis connection
│
├── models/
│   ├── coffee.py             # Coffee DB model
│   ├── conversation.py       # Conversation/session model
│   └── user_profile.py       # Extracted user preference model
│
├── services/
│   ├── llm_service.py        # Claude/OpenAI API wrapper + streaming
│   ├── retrieval_service.py  # Query DB, semantic search, rank results
│   ├── profile_service.py    # Extract user preferences from chat
│   └── affiliate_service.py  # Map coffee → affiliate link
│
├── scraper/
│   ├── spiders/
│   │   ├── bluebottle.py
│   │   ├── onibuscoffee.py
│   │   └── base_spider.py    # shared logic
│   ├── normalizer.py         # standardize scraped data
│   ├── scheduler.py          # Celery tasks for periodic scraping
│   └── ingestion.py          # cleaned data → PostgreSQL
│
└── prompts/
    ├── system_prompt.txt     # Core chatbot personality + rules
    └── extraction_prompt.txt # Prompt to pull user prefs from messages