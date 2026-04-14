from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.templating import Jinja2Templates

from agent.browser_agent import run_agent
from backend.database import create_user
from backend.database import dashboard_stats
from backend.database import init_db
from backend.database import list_users
from backend.database import assign_license
from backend.database import available_licenses
from backend.database import list_license_assignments
from backend.database import reset_password
from backend.database import unlock_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.automation_jobs = {}
    app.state.automation_lock = Lock()
    yield


app = FastAPI(title="Mock IT Admin Panel", lifespan=lifespan)
templates = Jinja2Templates(directory="backend/templates")


class AutomationRequest(BaseModel):
    prompt: str


def ensure_automation_state(app_instance: FastAPI) -> None:
    if not hasattr(app_instance.state, "automation_jobs"):
        app_instance.state.automation_jobs = {}
    if not hasattr(app_instance.state, "automation_lock"):
        app_instance.state.automation_lock = Lock()


def update_job_state(app_instance: FastAPI, job_id: str, **fields: Any) -> None:
    ensure_automation_state(app_instance)
    lock: Lock = app_instance.state.automation_lock
    with lock:
        current = app_instance.state.automation_jobs.get(job_id, {})
        current.update(fields)
        app_instance.state.automation_jobs[job_id] = current


def append_job_log(app_instance: FastAPI, job_id: str, message: str) -> None:
    ensure_automation_state(app_instance)
    lock: Lock = app_instance.state.automation_lock
    with lock:
        current = app_instance.state.automation_jobs.get(job_id, {})
        logs = list(current.get("logs", []))
        logs.append(message)
        current["logs"] = logs[-80:]
        current["last_message"] = message
        app_instance.state.automation_jobs[job_id] = current


def run_automation_job(app_instance: FastAPI, job_id: str, prompt: str, base_url: str) -> None:
    update_job_state(app_instance, job_id, status="running", result=None, error=None)

    def progress_logger(message: str) -> None:
        append_job_log(app_instance, job_id, message)

    try:
        result = asyncio.run(
            run_agent(
                request=prompt,
                base_url=base_url,
                headless=True,
                progress_callback=progress_logger,
            )
        )
    except Exception as exc:
        append_job_log(app_instance, job_id, f"Task failed: {exc}")
        update_job_state(app_instance, job_id, status="failed", error=str(exc))
        return
    append_job_log(app_instance, job_id, f"Final result: {result}")
    update_job_state(app_instance, job_id, status="completed", result=result, error=None)


def redirect_with_message(route_name: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query_parts: list[str] = []
    if message:
        query_parts.append(f"message={message.replace(' ', '+')}")
    if error:
        query_parts.append(f"error={error.replace(' ', '+')}")
    query_string = f"?{'&'.join(query_parts)}" if query_parts else ""
    return RedirectResponse(url=app.url_path_for(route_name) + query_string, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": dashboard_stats(),
            "message": message,
            "error": error,
            "active_page": "dashboard",
            "title": "Dashboard | Helix IT Ops",
        },
    )


@app.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "users": list_users(),
            "message": message,
            "error": error,
            "active_page": "users",
            "title": "Users | Helix IT Ops",
        },
    )


@app.get("/security", response_class=HTMLResponse)
def security_page(
    request: Request,
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    return templates.TemplateResponse(
        request=request,
        name="security.html",
        context={
            "users": list_users(),
            "message": message,
            "error": error,
            "active_page": "security",
            "title": "Security | Helix IT Ops",
        },
    )


@app.get("/licenses", response_class=HTMLResponse)
def licenses_page(
    request: Request,
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    return templates.TemplateResponse(
        request=request,
        name="licenses.html",
        context={
            "licenses": available_licenses(),
            "assignments": list_license_assignments(),
            "message": message,
            "error": error,
            "active_page": "licenses",
            "title": "Licenses | Helix IT Ops",
        },
    )


@app.post("/users/create")
def create_user_action(
    full_name: str = Form(...),
    email: str = Form(...),
    department: str = Form(...),
):
    try:
        create_user(full_name=full_name, email=email, department=department)
    except ValueError as exc:
        return redirect_with_message("users_page", error=str(exc))
    return redirect_with_message("users_page", message="User created successfully")


@app.post("/security/reset-password")
def reset_password_action(email: str = Form(...)):
    try:
        reset_password(email=email)
    except LookupError as exc:
        return redirect_with_message("security_page", error=str(exc))
    return redirect_with_message("security_page", message="Password reset successfully")


@app.post("/security/unlock-user")
def unlock_user_action(email: str = Form(...)):
    try:
        unlock_user(email=email)
    except LookupError as exc:
        return redirect_with_message("security_page", error=str(exc))
    return redirect_with_message("security_page", message="User unlocked successfully")


@app.post("/licenses/assign")
def assign_license_action(email: str = Form(...), license_name: str = Form(...)):
    try:
        assign_license(email=email, license_name=license_name)
    except (LookupError, ValueError) as exc:
        return redirect_with_message("licenses_page", error=str(exc))
    return redirect_with_message("licenses_page", message="License assigned successfully")


@app.post("/automation/jobs")
async def create_automation_job(payload: AutomationRequest, request: Request):
    prompt = payload.prompt.strip()
    if not prompt:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Prompt is required."})

    job_id = str(uuid4())
    base_url = str(request.base_url).rstrip("/")
    update_job_state(
        request.app,
        job_id,
        id=job_id,
        prompt=prompt,
        status="queued",
        result=None,
        error=None,
        logs=[f"Job created for prompt: {prompt}"],
        last_message="Job created and waiting to start",
    )
    asyncio.create_task(asyncio.to_thread(run_automation_job, request.app, job_id, prompt, base_url))
    return {"job_id": job_id, "status": "queued"}


@app.get("/automation/jobs/{job_id}")
async def get_automation_job(job_id: str, request: Request):
    ensure_automation_state(request.app)
    job = request.app.state.automation_jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Job not found."})
    return job
