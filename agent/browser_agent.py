from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page
from playwright.async_api import async_playwright

from agent.llm import generate_json


SUPPORTED_DEPARTMENTS = ["IT", "HR", "Finance", "Operations", "Sales"]
SUPPORTED_LICENSES = ["Google Workspace", "Slack", "Zoom", "VPN", "Okta"]


@dataclass
class SupportTask:
    action: str
    email: str
    full_name: str = ""
    department: str = ""
    license_name: str = ""


def parse_request(request: str) -> SupportTask:
    local_task = parse_request_locally(request)
    if local_task.action and local_task.email:
        return local_task

    prompt = f"""
You are an IT support dispatcher.
Convert the request below into a JSON object.

Supported actions:
- create_user
- reset_password
- unlock_user
- assign_license
- ensure_user_and_assign_license

If any field is unavailable, return an empty string for it.
Choose department from this fixed list when possible: {", ".join(SUPPORTED_DEPARTMENTS)}.
Choose license_name from this fixed list when possible: {", ".join(SUPPORTED_LICENSES)}.

Request: "{request}"

Return only JSON with this exact schema:
{{
  "action": "create_user | reset_password | unlock_user | assign_license | ensure_user_and_assign_license",
  "email": "user email",
  "full_name": "employee name",
  "department": "IT | HR | Finance | Operations | Sales",
  "license_name": "Google Workspace | Slack | Zoom | VPN | Okta"
}}
"""
    payload = generate_json(prompt)
    return SupportTask(
        action=str(payload.get("action", "")).strip(),
        email=str(payload.get("email", "")).strip().lower(),
        full_name=str(payload.get("full_name", "")).strip(),
        department=str(payload.get("department", "")).strip(),
        license_name=str(payload.get("license_name", "")).strip(),
    )


def parse_request_locally(request: str) -> SupportTask:
    request_lower = request.lower()
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", request_lower)
    email = email_match.group(0) if email_match else ""

    department = next(
        (
            item
            for item in SUPPORTED_DEPARTMENTS
            if re.search(rf"\b{re.escape(item.lower())}\b", request_lower)
        ),
        "",
    )
    license_name = next(
        (
            item
            for item in SUPPORTED_LICENSES
            if re.search(rf"\b{re.escape(item.lower())}\b", request_lower)
        ),
        "",
    )

    full_name = ""
    named_match = re.search(
        r"named\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}?)(?=\s+(?:with|in|for|then)\b|$)",
        request,
        flags=re.IGNORECASE,
    )
    if named_match:
        full_name = named_match.group(1).strip()
    elif email:
        local_part = email.split("@", 1)[0]
        full_name = " ".join(part.capitalize() for part in re.split(r"[._-]+", local_part) if part)

    if ("if not" in request_lower or "if missing" in request_lower or "if user exists" in request_lower) and "assign" in request_lower:
        action = "ensure_user_and_assign_license"
    elif "assign" in request_lower and "license" in request_lower:
        action = "assign_license"
    elif "unlock" in request_lower:
        action = "unlock_user"
    elif "reset" in request_lower and "password" in request_lower:
        action = "reset_password"
    elif "create" in request_lower and "user" in request_lower:
        action = "create_user"
    else:
        action = ""

    return SupportTask(
        action=action,
        email=email,
        full_name=full_name,
        department=department or "IT",
        license_name=license_name,
    )


async def annotate_page(page: Page) -> list[dict[str, Any]]:
    return await page.evaluate(
        """
        () => {
          const interactiveSelectors = ['a', 'button', 'input', 'select', 'textarea'];
          const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')));
          let counter = 1;
          const visibleElements = [];

          for (const element of elements) {
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            const hidden = style.visibility === 'hidden' || style.display === 'none';
            const disabled = element.disabled === true;
            const visible = rect.width > 0 && rect.height > 0 && !hidden;

            if (!visible || disabled) {
              continue;
            }

            const label = element.labels && element.labels.length
              ? Array.from(element.labels).map((item) => item.innerText.trim()).join(' ')
              : '';
            const text = (element.innerText || element.value || element.placeholder || element.getAttribute('aria-label') || label || '').trim();
            const optionValues = element.tagName.toLowerCase() === 'select'
              ? Array.from(element.options).map((option) => option.text.trim()).filter(Boolean)
              : [];
            const form = element.closest('form');
            const panel = element.closest('article, section, div');
            const formText = form ? (form.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 240) : '';
            const panelText = panel ? (panel.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 240) : '';

            element.setAttribute('data-agent-id', String(counter));
            visibleElements.push({
              id: String(counter),
              tag: element.tagName.toLowerCase(),
              type: (element.getAttribute('type') || '').toLowerCase(),
              text,
              name: element.getAttribute('name') || '',
              label,
              value: element.value || '',
              href: element.getAttribute('href') || '',
              options: optionValues,
              form_text: formText,
              panel_text: panelText
            });
            counter += 1;
          }

          return visibleElements;
        }
        """
    )


async def current_page_summary(page: Page) -> dict[str, Any]:
    interactive_elements = await annotate_page(page)
    body_text = await page.locator("body").inner_text()
    return {
        "title": await page.title(),
        "url": page.url,
        "body_text": " ".join(body_text.split())[:3000],
        "interactive_elements": interactive_elements,
    }


def build_next_action_prompt(task: SupportTask, page_state: dict[str, Any], history: list[dict[str, Any]]) -> str:
    return f"""
You are controlling a browser to complete an IT support request using a mock admin panel.
Act like a careful human operator. Do not invent success unless the UI confirms it.

Task JSON:
{json.dumps(task.__dict__, indent=2)}

Recent action history:
{json.dumps(history[-6:], indent=2)}

Current page:
{json.dumps(page_state, indent=2)}

Allowed action formats:
1. {{"action": "click", "target_id": "3"}}
2. {{"action": "type", "target_id": "5", "text": "john@company.com"}}
3. {{"action": "select", "target_id": "6", "value": "Finance"}}
4. {{"action": "done", "reason": "short summary of completed work"}}

Rules:
- Use only target ids that appear in interactive_elements.
- Prefer navigation links before random clicks.
- For create_user, fill full name, email, department, then submit.
- For reset_password, go to the security page if needed, fill the user email, then submit reset.
- For unlock_user, go to the security page if needed, fill the unlock email field, then submit unlock.
- For assign_license, go to the licenses page if needed, fill the user email, choose the license, then submit.
- For ensure_user_and_assign_license, first verify whether the user already appears in the directory. If not, create the user, then navigate to Licenses and assign the requested license.
- If the page shows a success flash message matching the task, return done.
- Return exactly one JSON object and nothing else.
"""


def find_element(
    interactive_elements: list[dict[str, Any]],
    *,
    tag: str | None = None,
    name: str | None = None,
    text_contains: str | None = None,
    href_contains: str | None = None,
    form_text_contains: str | None = None,
) -> dict[str, Any] | None:
    for element in interactive_elements:
        if tag and element.get("tag") != tag:
            continue
        if name and element.get("name") != name:
            continue
        if text_contains and text_contains.lower() not in (element.get("text") or "").lower():
            continue
        if href_contains and href_contains.lower() not in (element.get("href") or "").lower():
            continue
        if form_text_contains and form_text_contains.lower() not in (element.get("form_text") or "").lower():
            continue
        return element
    return None


def success_message_for(task: SupportTask) -> str:
    return {
        "create_user": "user created successfully",
        "reset_password": "password reset successfully",
        "unlock_user": "user unlocked successfully",
        "assign_license": "license assigned successfully",
        "ensure_user_and_assign_license": "license assigned successfully",
    }.get(task.action, "")


def terminal_outcome(task: SupportTask, body_text: str) -> tuple[str, str] | None:
    if "user created successfully" in body_text and task.action == "create_user":
        return ("done", f"Created user {task.email}")
    if "password reset successfully" in body_text and task.action == "reset_password":
        return ("done", f"Reset password for {task.email}")
    if "user unlocked successfully" in body_text and task.action == "unlock_user":
        return ("done", f"Unlocked user {task.email}")
    if "license assigned successfully" in body_text and task.action in {"assign_license", "ensure_user_and_assign_license"}:
        return ("done", f"Assigned {task.license_name} to {task.email}")

    if "a user with that email already exists." in body_text:
        if task.action == "create_user":
            return ("done", f"User {task.email} already exists")
        if task.action == "ensure_user_and_assign_license":
            return ("continue", "User already exists, continue to license assignment")

    if "license is already assigned to this user." in body_text and task.action in {"assign_license", "ensure_user_and_assign_license"}:
        return ("done", f"{task.license_name} is already assigned to {task.email}")

    if "user not found." in body_text and task.action in {"reset_password", "unlock_user", "assign_license"}:
        return ("error", f"User {task.email} was not found in the admin panel")

    if "unsupported license." in body_text:
        return ("error", f"Unsupported license requested: {task.license_name}")

    return None


def recent_repeated_actions(history: list[dict[str, Any]], threshold: int = 3) -> bool:
    recent = [entry.get("action") for entry in history if entry.get("action")]
    if len(recent) < threshold:
        return False
    tail = recent[-threshold:]
    return all(item == tail[0] for item in tail)


def next_action_locally(task: SupportTask, page_state: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    body_text = page_state["body_text"].lower()
    interactive_elements = page_state["interactive_elements"]

    outcome = terminal_outcome(task, body_text)
    if outcome:
        status, message = outcome
        if status == "done":
            return {"action": "done", "reason": message}
        if status == "error":
            raise RuntimeError(message)

    if recent_repeated_actions(history):
        raise RuntimeError(
            f"Agent got stuck repeating the same action on {page_state['url']}. "
            f"Page message: {page_state['body_text'][:220]}"
        )

    if task.action == "create_user":
        return next_action_for_create(task, page_state)
    if task.action == "reset_password":
        return next_action_for_reset(task, page_state)
    if task.action == "unlock_user":
        return next_action_for_unlock(task, page_state)
    if task.action == "assign_license":
        return next_action_for_license(task, page_state)
    if task.action == "ensure_user_and_assign_license":
        if outcome and outcome[0] == "continue":
            licenses_link = find_element(interactive_elements, tag="a", href_contains="/licenses")
            if licenses_link:
                return {"action": "click", "target_id": licenses_link["id"]}

        if "/licenses" in page_state["url"] or "license administration" in body_text:
            return next_action_for_license(task, page_state)

        if "/users" in page_state["url"] or "user administration" in body_text:
            if task.email.lower() in body_text:
                license_link = find_element(interactive_elements, tag="a", href_contains="/licenses")
                if license_link:
                    return {"action": "click", "target_id": license_link["id"]}
            return next_action_for_create(task, page_state)

        users_link = find_element(interactive_elements, tag="a", href_contains="/users")
        if users_link:
            return {"action": "click", "target_id": users_link["id"]}

    raise ValueError(f"Unsupported task action: {task.action}")


def next_action_for_create(task: SupportTask, page_state: dict[str, Any]) -> dict[str, Any]:
    interactive_elements = page_state["interactive_elements"]
    body_text = page_state["body_text"].lower()
    if "/users" not in page_state["url"] and "user administration" not in body_text:
        users_link = find_element(interactive_elements, tag="a", href_contains="/users")
        if users_link:
            return {"action": "click", "target_id": users_link["id"]}

    name_input = find_element(interactive_elements, tag="input", name="full_name")
    if name_input and name_input.get("value", "").strip() != task.full_name:
        return {"action": "type", "target_id": name_input["id"], "text": task.full_name}

    email_input = find_element(interactive_elements, tag="input", name="email")
    if email_input and email_input.get("value", "").strip().lower() != task.email:
        return {"action": "type", "target_id": email_input["id"], "text": task.email}

    department_select = find_element(interactive_elements, tag="select", name="department")
    if department_select and task.department:
        current_value = department_select.get("value", "").strip()
        if current_value != task.department:
            return {"action": "select", "target_id": department_select["id"], "value": task.department}

    submit_button = find_element(interactive_elements, tag="button", text_contains="create user")
    if submit_button:
        return {"action": "click", "target_id": submit_button["id"]}

    raise RuntimeError("Could not find the create user controls on the page.")


def next_action_for_reset(task: SupportTask, page_state: dict[str, Any]) -> dict[str, Any]:
    interactive_elements = page_state["interactive_elements"]
    body_text = page_state["body_text"].lower()
    if "/security" not in page_state["url"] and "security operations" not in body_text:
        security_link = find_element(interactive_elements, tag="a", href_contains="/security")
        if security_link:
            return {"action": "click", "target_id": security_link["id"]}

    email_input = find_element(interactive_elements, tag="input", name="email", form_text_contains="reset password")
    if email_input and email_input.get("value", "").strip().lower() != task.email:
        return {"action": "type", "target_id": email_input["id"], "text": task.email}

    submit_button = find_element(interactive_elements, tag="button", text_contains="reset password")
    if submit_button:
        return {"action": "click", "target_id": submit_button["id"]}

    raise RuntimeError("Could not find the reset password controls on the page.")


def next_action_for_unlock(task: SupportTask, page_state: dict[str, Any]) -> dict[str, Any]:
    interactive_elements = page_state["interactive_elements"]
    body_text = page_state["body_text"].lower()
    if "/security" not in page_state["url"] and "security operations" not in body_text:
        security_link = find_element(interactive_elements, tag="a", href_contains="/security")
        if security_link:
            return {"action": "click", "target_id": security_link["id"]}

    email_input = find_element(interactive_elements, tag="input", name="email", form_text_contains="unlock account")
    if email_input and email_input.get("value", "").strip().lower() != task.email:
        return {"action": "type", "target_id": email_input["id"], "text": task.email}

    submit_button = find_element(interactive_elements, tag="button", text_contains="unlock user")
    if submit_button:
        return {"action": "click", "target_id": submit_button["id"]}

    raise RuntimeError("Could not find the unlock user controls on the page.")


def next_action_for_license(task: SupportTask, page_state: dict[str, Any]) -> dict[str, Any]:
    interactive_elements = page_state["interactive_elements"]
    body_text = page_state["body_text"].lower()
    if "/licenses" not in page_state["url"] and "license administration" not in body_text:
        licenses_link = find_element(interactive_elements, tag="a", href_contains="/licenses")
        if licenses_link:
            return {"action": "click", "target_id": licenses_link["id"]}

    email_input = find_element(interactive_elements, tag="input", name="email")
    if email_input and email_input.get("value", "").strip().lower() != task.email:
        return {"action": "type", "target_id": email_input["id"], "text": task.email}

    license_select = find_element(interactive_elements, tag="select", name="license_name")
    if license_select and task.license_name:
        current_value = license_select.get("value", "").strip()
        if current_value != task.license_name:
            return {"action": "select", "target_id": license_select["id"], "value": task.license_name}

    submit_button = find_element(interactive_elements, tag="button", text_contains="assign license")
    if submit_button:
        return {"action": "click", "target_id": submit_button["id"]}

    raise RuntimeError("Could not find the assign license controls on the page.")


async def execute_action(page: Page, action: dict[str, Any]) -> str:
    action_name = action.get("action")
    if action_name == "click":
        target_id = str(action["target_id"])
        await page.locator(f"[data-agent-id='{target_id}']").click()
        return f"Clicked element {target_id}"
    if action_name == "type":
        target_id = str(action["target_id"])
        await page.locator(f"[data-agent-id='{target_id}']").fill(str(action.get("text", "")))
        return f"Typed into element {target_id}"
    if action_name == "select":
        target_id = str(action["target_id"])
        locator = page.locator(f"[data-agent-id='{target_id}']")
        options = await locator.locator("option").all_inner_texts()
        requested_value = str(action.get("value", "")).strip().lower()
        matched_option = next(
            (option for option in options if option.strip().lower() == requested_value),
            action.get("value", ""),
        )
        await locator.select_option(label=str(matched_option))
        return f"Selected option on element {target_id}"
    if action_name == "done":
        return str(action.get("reason", "Task completed"))
    raise ValueError(f"Unsupported action: {action}")


async def run_agent(request: str, base_url: str = "http://127.0.0.1:8000", headless: bool = False) -> str:
    task = parse_request(request)
    if task.action not in {"create_user", "reset_password", "unlock_user", "assign_license", "ensure_user_and_assign_license"}:
        raise ValueError(f"Unsupported request: {request}")
    if not task.email:
        raise ValueError("The agent could not identify a user email from the request.")
    if task.action in {"assign_license", "ensure_user_and_assign_license"} and not task.license_name:
        raise ValueError("The request must include one of these licenses: Google Workspace, Slack, Zoom, VPN, Okta.")

    history: list[dict[str, Any]] = [{"step": 0, "result": f"Parsed task as {task.__dict__}"}]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(base_url, wait_until="networkidle")

        final_message = ""
        for step in range(1, 20):
            page_state = await current_page_summary(page)
            next_action = next_action_locally(task, page_state, history)

            result = await execute_action(page, next_action)
            history.append({"step": step, "action": next_action, "result": result})
            print(f"Step {step}: {result}")

            if next_action["action"] == "done":
                final_message = result
                break

            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(400)
        else:
            raise RuntimeError("Agent reached the step limit before completing the task.")

        await browser.close()

    return final_message


def main() -> None:
    request = " ".join(sys.argv[1:]).strip() or input("Enter IT support request: ").strip()
    summary = asyncio.run(run_agent(request=request))
    print(summary)


if __name__ == "__main__":
    main()
