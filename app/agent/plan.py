"""PlanSkill: a short 1–9 pointer outline of how this session will go."""

from __future__ import annotations

from app.whatsapp.payloads import InteractiveButtonsPayload, ReplyButton

PLAN_GO = "plan:go"
PLAN_EDIT = "plan:edit"
PLAN_SKIP = "plan:skip"

PLAN_BUTTON_IDS = {PLAN_GO, PLAN_EDIT, PLAN_SKIP}

MAX_POINTERS = 9
MIN_POINTERS = 1


def normalise_pointers(pointers: list[str]) -> list[str]:
    cleaned = [p.strip() for p in pointers if p and p.strip()]
    return cleaned[:MAX_POINTERS]


def format_plan_body(goal: str, pointers: list[str]) -> str:
    steps = normalise_pointers(pointers)
    lines: list[str] = ["Here's how we can do this."]
    if goal.strip():
        lines.append(f"*{goal.strip()}*")
    lines.append("")
    for i, pointer in enumerate(steps, 1):
        lines.append(f"{i}. {pointer}")
    lines.append("")
    lines.append("Go follows this. Change plan to edit. Just do it skips the outline.")
    body = "\n".join(lines)
    return body[:1024]


def plan_buttons_payload(goal: str, pointers: list[str]) -> InteractiveButtonsPayload:
    return InteractiveButtonsPayload(
        body_text=format_plan_body(goal, pointers),
        buttons=[
            ReplyButton(id=PLAN_GO, title="Go"),
            ReplyButton(id=PLAN_EDIT, title="Change plan"),
            ReplyButton(id=PLAN_SKIP, title="Just do it"),
        ],
    )


def prompt_for_plan_tap(button_id: str, pointers: list[str], goal: str) -> str:
    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(pointers, 1)) or "(no pointers yet)"
    goal_line = goal.strip() or "(none)"
    if button_id == PLAN_GO:
        return (
            "The user approved the plan. Execute it now, following these pointers in order. "
            "Skip a pointer if it no longer fits; do not restart the outline.\n"
            f"Goal: {goal_line}\n{numbered}"
        )
    if button_id == PLAN_EDIT:
        return (
            "The user wants to change the plan. Ask what to change in one short message, "
            "then call propose_plan with the revised 1–9 pointers. Do not start the work yet.\n"
            f"Current goal: {goal_line}\nCurrent pointers:\n{numbered}"
        )
    return (
        "The user skipped the outline. Do the work now without walking the pointers. "
        "Use the goal and brand card; ask only if a decision is blocking.\n"
        f"Goal: {goal_line}"
    )
