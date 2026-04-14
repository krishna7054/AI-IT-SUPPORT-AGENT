# AI IT Support Agent Assignment

This project delivers a small but realistic IT support automation demo:

- A mock IT admin panel built with FastAPI and SQLite
- An AI browser agent powered by Gemini and Playwright
- End-to-end task execution through the UI, without hardcoded task-specific DOM flows or backend API shortcuts

## Features

- Create a new user account
- Reset a user's password
- Unlock a locked user account
- Assign a SaaS license to a user
- Bonus multi-step flow: check if a user exists, create them if needed, then assign a license
- Persist data in SQLite so changes remain visible between runs
- Seed realistic starter users for demos

## Tech stack

- `FastAPI` for the mock admin panel
- `Jinja2` for server-rendered HTML pages
- `SQLite` for persistence
- `Playwright` for browser automation
- `Gemini` for natural-language request parsing and browser decision-making
- Local fallback parsing/planning when Gemini quota is exhausted

## Project structure

```text
.
|-- agent/
|   |-- __main__.py
|   |-- browser_agent.py
|   `-- llm.py
|-- backend/
|   |-- __init__.py
|   |-- database.py
|   |-- main.py
|   `-- templates/
|       |-- base.html
|       |-- dashboard.html
|       |-- licenses.html
|       |-- security.html
|       `-- users.html
|-- scripts/
|   `-- reset_demo_data.py
|-- data/
|   `-- it_admin.db         # created automatically at runtime
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

3. Create an environment file:

```bash
copy .env.example .env
```

4. Add your Gemini API key to `.env`:

```env
GEMINI_API_KEY=your_api_key_here
```

Optional:

```env
ENABLE_GEMINI=true
```

By default, the project runs in local deterministic mode so it is not blocked by Gemini free-tier quota. If you set `ENABLE_GEMINI=true`, the request parser can use Gemini when local parsing is ambiguous.

## Run the app

Optional: reset to the seeded demo users before a recording:

```bash
python scripts/reset_demo_data.py
```

Start the admin panel:

```bash
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Run the agent

In a second terminal, execute:

```bash
python -m agent
```

Or pass the request inline:

```bash
python -m agent "reset password for john@company.com"
```

Example prompts:

- `create a new user named Sarah Khan with email sarah@company.com in Finance`
- `reset password for john@company.com`
- `unlock account for priya@company.com`
- `assign Slack license to alice@company.com`
- `check if mohit@company.com exists, if not create him in IT, then assign a Slack license`

The agent:

- Parses the natural-language IT request with Gemini
- Falls back to local parsing/planning if Gemini is rate-limited
- Opens the browser with Playwright
- Reads the current page state and visible controls
- Chooses the next action from the live UI state
- Finishes only after the success message is visible

## Architecture summary

### 1. Mock admin panel

- `backend/main.py` defines the web routes and form actions.
- `backend/database.py` initializes SQLite, seeds demo users, and handles user operations.
- `backend/database.py` also stores license assignments for the bonus scenario.
- `backend/templates/` contains the admin console pages.

### 2. AI browser agent

- `agent/browser_agent.py` contains the full agent loop.
- The agent does not use task-specific selectors like "click reset page then fill this field".
- Instead, it inspects the currently visible interactive elements, sends that page state to Gemini, and executes the returned generic action:
  - `click`
  - `type`
  - `select`
  - `done`
- The bonus flow adds conditional logic:
  - Check whether the user exists on the Users page
  - Create them only if needed
  - Continue to the Licenses page and assign the requested product

### 3. Why this fits the assignment

- The admin panel is functional and easy to demo.
- The agent performs the task through the browser like a human operator.
- There are no backend API shortcuts for the automation flow.
- The approach is fast to explain in a 2-minute Loom while still showing clear architecture choices.

## Suggested Loom flow

1. Show the dashboard and seeded users.
2. Run: `create a new user named Sarah Khan with email sarah@company.com in Finance`
3. Show that the new user appears in the directory.
4. Run: `reset password for john@company.com`
5. Show the updated password on the Security page.
6. Run: `check if mohit@company.com exists, if not create him in IT, then assign a Slack license`
7. Optional fourth task: `unlock account for priya@company.com`
8. Spend the last 30-40 seconds explaining:
   - FastAPI + SQLite mock panel
   - Gemini with a local fallback for request understanding and next-step planning
   - Playwright for browser execution
   - Generic page-state-driven action loop instead of hardcoded flows
   - Bonus conditional workflow for create-if-missing then assign-license

## Notes

- This repo is ready for GitHub.
- The SQLite database is ignored in git and is created automatically.
- If Gemini quota is exhausted, the agent automatically falls back to deterministic local parsing and planning for the supported task set.
