# AOS SBE Governance Training Module

This workspace contains a backend-backed FastAPI/Jinja training module for SBE governance training. It replaces standalone browser-only storage with central submissions, server-side scoring, facilitator dashboards, and secure AI grading hooks.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- Participant module: http://127.0.0.1:8000/training/sbe-governance-2026
- Facilitator dashboard: http://127.0.0.1:8000/facilitator/sbe-governance-2026
- Facilitator slides: http://127.0.0.1:8000/facilitator/sbe-governance-2026/slides

Default facilitator passcode:

```text
aos-demo-facilitator
```

Set `FACILITATOR_PASSCODE` and `AOS_TRAINING_SECRET` in production.

## AI Grading

Open-ended grading happens server-side only. Hidden rubrics and expected answers live in the database and Python seed file; they are not rendered into participant pages or frontend JavaScript.

Local development defaults to a server-side rubric grader so the module works without an API key. To use OpenAI server-side grading:

```bash
export AOS_AI_PROVIDER=openai
export OPENAI_API_KEY=...
export AOS_AI_MODEL=gpt-4o-mini
uvicorn app.main:app --reload
```

Never place API keys, hidden rubrics, or expected answer guides in frontend templates or JavaScript.

## Implemented Endpoints

- `POST /api/training/sessions`
- `GET /api/training/sessions/{session_id}`
- `POST /api/training/sessions/{session_id}/submissions`
- `POST /api/training/submissions/{submission_id}/grade`
- `GET /api/training/sessions/{session_id}/dashboard`
- `GET /api/training/sessions/{session_id}/export.csv`
- `GET /api/training/sessions/{session_id}/export.json`
- `GET /api/training/sessions/{session_id}/export.pdf`
- `POST /api/training/sessions/{session_id}/discussion-summary`

## Data Storage

By default, local SQLite data is stored at:

```text
data/aos_training.db
```

For Replit/Supabase, set one of these environment variables to the Supabase
Postgres connection string:

```text
AOS_TRAINING_DATABASE_URL
SUPABASE_DATABASE_URL
DATABASE_URL
SUPABASE_DB_URL
POSTGRES_URL
```

`AOS_TRAINING_DATABASE_URL` is preferred because it avoids accidentally sharing
the broader AOS app database setting unless that is intentional. The module also
accepts the existing AOS `SUPABASE_DATABASE_URL` secret.

For Replit, Supabase's shared pooler connection string is usually safer than
the direct `db.<project-ref>.supabase.co` host, because the direct host may
require IPv6. The module adds `sslmode=require` automatically when the Postgres
URL does not specify an SSL mode. For the transaction pooler on port `6543`,
the module disables Psycopg prepared statements because Supavisor transaction
mode does not support them.

To inspect the configured database without printing the secret:

```bash
python scripts/check_database.py
```

## Replit Workflow

The parent AOS Replit has a dedicated workflow named:

```text
Start SBE training module
```

It starts this standalone FastAPI module on local port `5055`, which the parent
Replit maps to external port `3000`.

The schema includes:

- `training_sessions`
- `training_questions`
- `training_submissions`
- `training_answers`

## Coverage

The seeded session includes:

- Three rounds:
  - Round 1 live core round
  - Round 2 self-study practice
  - Round 3 advanced scenarios
- Financial policy discipline
- Principal authority for academic decisions and school operations
- Management escalation
- Cross-department workflows
- Emergency and urgency classification
- Case tags: Academic / Principal, Finance, CX / School Admin, HR, Technical / IT, Management, Emergency / Urgent, Not Urgent, Cross-Department
- 12 required case-tagging scenarios
- 5 workflow-card questions with short remarks, hidden rubrics, and facilitator-only sample answers
- Facilitator dashboard metrics, missed tags, discussion flags, CSV/JSON/PDF exports, and AI discussion summary generation

## Round Links

- Round 1: http://127.0.0.1:8000/training/sbe-governance-2026?round=1
- Round 2: http://127.0.0.1:8000/training/sbe-governance-2026?round=2
- Round 3: http://127.0.0.1:8000/training/sbe-governance-2026?round=3

Round 1 is intended for live facilitated discussion. Rounds 2 and 3 can be completed independently later.
