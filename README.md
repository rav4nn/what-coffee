# What Coffee

An AI-powered specialty coffee recommendation chatbot. Tell it your brew method and flavor preferences — it recommends Indian specialty coffees you can buy online.

**Live demo:** [what-coffee-xi.vercel.app](https://what-coffee-xi.vercel.app)

---

## What it does

- Asks 3 guided questions (experience level, brew method, flavor profile) with clickable option chips
- Queries a database of Indian specialty coffees scraped from roasters like Blue Tokai, Subko, Corridor Seven, Black Baza, and Araku
- Uses Claude (Anthropic) to generate personalized recommendations with purchase links

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 + React 19 |
| Backend | FastAPI (Python) |
| Database | SQLite via Peewee ORM |
| LLM | Claude API (Anthropic) |
| Frontend hosting | Vercel |
| Backend hosting | Render |

## Project structure

```
what-coffee/
├── backend/
│   ├── main.py                  # FastAPI app, chat endpoint
│   ├── coffees.db               # SQLite database
│   ├── models/coffee.py         # Database model
│   ├── services/
│   │   └── retrieval_service.py # Coffee search logic
│   ├── scraper/                 # Data collection scripts (local use)
│   └── prompts/
│       └── system_prompt.txt    # LLM system prompt
└── frontend/
    └── app/
        └── page.tsx             # Chat UI
```

## Running locally

**Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

Create a `backend/.env` file with:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Deployment

- **Frontend:** Vercel — set root directory to `frontend`, add `NEXT_PUBLIC_API_URL` env variable pointing to the backend URL
- **Backend:** Render — set root directory to `backend`, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`, add `ANTHROPIC_API_KEY` env variable
