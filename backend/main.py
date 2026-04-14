from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request
from starlette.templating import Jinja2Templates

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
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Mock IT Admin Panel", lifespan=lifespan)
templates = Jinja2Templates(directory="backend/templates")


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
