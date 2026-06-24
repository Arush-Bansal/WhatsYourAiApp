def prompt_for_text_message(text_body: str) -> str:
    return f"User message:\n{text_body}"


def prompt_for_button_reply(button_id: str, button_title: str) -> str:
    return (
        "User tapped a quick-reply button.\n"
        f"button_id={button_id}\n"
        f"button_title={button_title}"
    )


def prompt_for_list_reply(
    row_id: str,
    title: str,
    description: str,
) -> str:
    lines = [
        "User chose a list row.",
        f"row_id={row_id}",
        f"title={title}",
    ]
    if description:
        lines.append(f"description={description}")
    return "\n".join(lines)


def prompt_for_slack_button_action(
    action_id: str,
    button_text: str,
    value: str,
) -> str:
    lines = [
        "User tapped an interactive button.",
        f"action_id={action_id}",
        f"button_text={button_text}",
    ]
    if value:
        lines.append(f"value={value}")
    return "\n".join(lines)


def prompt_for_slack_menu_selection(
    action_id: str,
    option_value: str,
    option_text: str,
) -> str:
    return (
        "User chose a menu option.\n"
        f"action_id={action_id}\n"
        f"option_value={option_value}\n"
        f"option_text={option_text}"
    )
