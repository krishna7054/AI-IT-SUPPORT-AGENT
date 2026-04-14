from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page
from playwright.async_api import async_playwright

from agent.llm import generate_json


SUPPORTED_DEPARTMENTS = ["IT", "HR", "Finance", "Operations", "Sales"]


@dataclass
class SupportTask:
    action: str
    email: str
    full_name: str = ""
    department: str = ""


def parse_request(request: str) -> SupportTask:
    prompt = f"""
You are an IT support dispatcher.
Convert the request below into a JSON object.

Supported actions:
- create_user
- reset_password
- unlock_user

If any field is unavailable, return an empty string for it.
Choose department from this fixed list when possible: {", ".join(SUPPORTED_DEPARTMENTS)}.

Request: "{request}"

Return only JSON with this exact schema:
{{
  "action": "create_user | reset_password | unlock_user",
  "email": "user email",
  "full_name": "employee name",
  "department": "IT | HR | Finance | Operations | Sales"
}}
"""
    payload = generate_json(prompt)
    return SupportTask(
        action=str(payload.get("action", "")).strip(),
        email=str(payload.get("email", "")).strip().lower(),
        full_name=str(payload.get("full_name", "")).strip(),
        department=str(payload.get("department", "")).strip(),
    )


async def annotate_page(page: Page) -> list[dict[str, Any]]:
    return await page.evaluate(
        """
        () => {
          const interactiveSelectors = [
            'a',
            'button',
            'input',
            'select',
            'textarea'
          ];

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
              options: optionValues
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
        "body_text": " ".join(body_text.split())[:2500],
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
- If the page shows a success flash message matching the task, return done.
- Return exactly one JSON object and nothing else.
"""


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
    if task.action not in {"create_user", "reset_password", "unlock_user"}:
        raise ValueError(f"Unsupported request: {request}")
    if not task.email:
        raise ValueError("The model could not identify a user email from the request.")

    history: list[dict[str, Any]] = [{"step": 0, "result": f"Parsed task as {task.__dict__}"}]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(base_url, wait_until="networkidle")

        final_message = ""
        for step in range(1, 13):
            page_state = await current_page_summary(page)
            llm_action = generate_json(build_next_action_prompt(task, page_state, history))
            result = await execute_action(page, llm_action)
            history.append({"step": step, "action": llm_action, "result": result})
            print(f"Step {step}: {result}")

            if llm_action["action"] == "done":
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
