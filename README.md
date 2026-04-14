# AI IT Support Agent Assignment

This project delivers a small but realistic IT support automation demo:

- A mock IT admin panel built with FastAPI and SQLite
- An AI browser agent powered by Gemini and Playwright
- End-to-end task execution through the UI, without hardcoded task-specific DOM flows or backend API shortcuts

## Features

- Create a new user account
- Reset a user's password
- Unlock a locked user account
- Persist data in SQLite so changes remain visible between runs
- Seed realistic starter users for demos

## Tech stack

- `FastAPI` for the mock admin panel
- `Jinja2` for server-rendered HTML pages
- `SQLite` for persistence
- `Playwright` for browser automation
- `Gemini` for natural-language request parsing and browser decision-making

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

The agent:

- Parses the natural-language IT request with Gemini
- Opens the browser with Playwright
- Reads the current page state and visible controls
- Chooses the next action from the live UI state
- Finishes only after the success message is visible

## Architecture summary

### 1. Mock admin panel

- `backend/main.py` defines the web routes and form actions.
- `backend/database.py` initializes SQLite, seeds demo users, and handles user operations.
- `backend/templates/` contains the admin console pages.

### 2. AI browser agent

- `agent/browser_agent.py` contains the full agent loop.
- The agent does not use task-specific selectors like "click reset page then fill this field".
- Instead, it inspects the currently visible interactive elements, sends that page state to Gemini, and executes the returned generic action:
  - `click`
  - `type`
  - `select`
  - `done`

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
6. Optional third task: `unlock account for priya@company.com`
7. Spend the last 30-40 seconds explaining:
   - FastAPI + SQLite mock panel
   - Gemini for request understanding and next-step planning
   - Playwright for browser execution
   - Generic page-state-driven action loop instead of hardcoded flows

## Notes

- This repo is ready for GitHub.
- The SQLite database is ignored in git and is created automatically.
- If Gemini returns malformed JSON, rerun the command once; the code validates model output and fails loudly rather than acting silently.
