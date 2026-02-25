# ☕ What Coffee

An AI-powered coffee recommendation chatbot that learns your preferences 
and recommends coffees in a personalized manner.

## Tech Stack
- **Backend:** Python / FastAPI
- **Frontend:** Next.js (React)
- **Database:** PostgreSQL + pgvector
- **LLM:** Claude API (Anthropic)
- **Scraping:** Playwright + Celery

## Documentation
- [System Architecture](docs/architecture.md)
- [Database Schema](docs/database-schema.md)
- [Roadmap](docs/roadmap.md)

## Setup
_Instructions coming as the project develops._
```

---

## Step 7: Set Up Your .gitignore

Open `.gitignore` and paste this:
```
# Python
__pycache__/
*.pyc
*.pyo
.env
venv/
.venv/
*.egg-info/
dist/

# Node / Next.js
node_modules/
.next/
.env.local
.env.production

# VS Code
.vscode/settings.json

# Database
*.sqlite
*.db

# Secrets
.env
*.pem
*.key
