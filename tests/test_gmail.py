import base64

from app.gmail.parser import (
    extract_body_plain,
    iter_history_message_ids,
    message_has_label,
    parse_incoming_message,
)
from app.gmail.payloads import GmailReplyPayload, build_reply_raw, extract_email_address


def _encode_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _sample_message(
    *,
    from_header: str = "Customer <customer@example.com>",
    subject: str = "Appointment question",
    body: str = "Hello, do you accept insurance?",
    labels: list[str] | None = None,
) -> dict:
    return {
        "id": "msg123",
        "threadId": "thread456",
        "labelIds": labels or ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": from_header},
                {"name": "To", "value": "support@dental.com"},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": "<incoming@example.com>"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _encode_body(body)},
        },
    }


def test_extract_email_address():
    assert extract_email_address("Jane Doe <jane@example.com>") == "jane@example.com"
    assert extract_email_address("plain@example.com") == "plain@example.com"


def test_extract_body_plain_from_text_part():
    message = _sample_message(body="Need a cleaning appointment.")
    assert extract_body_plain(message) == "Need a cleaning appointment."


def test_extract_body_plain_prefers_plain_over_html():
    message = {
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": _encode_body("Plain body")},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": _encode_body("<p>HTML body</p>")},
                },
            ],
        }
    }
    assert extract_body_plain(message) == "Plain body"


def test_parse_incoming_message_success():
    parsed = parse_incoming_message(
        _sample_message(),
        mailbox_email="support@dental.com",
    )
    assert parsed is not None
    message_id, thread_id, from_email, _to, subject, body, msg_header = parsed
    assert message_id == "msg123"
    assert thread_id == "thread456"
    assert from_email == "customer@example.com"
    assert subject == "Appointment question"
    assert "insurance" in body
    assert msg_header == "<incoming@example.com>"


def test_parse_incoming_message_skips_self_sent():
    parsed = parse_incoming_message(
        _sample_message(from_header="support@dental.com"),
        mailbox_email="support@dental.com",
    )
    assert parsed is None


def test_parse_incoming_message_skips_non_inbox():
    parsed = parse_incoming_message(
        _sample_message(labels=["SENT"]),
        mailbox_email="support@dental.com",
    )
    assert parsed is None


def test_message_has_label():
    message = _sample_message(labels=["INBOX", "UNREAD"])
    assert message_has_label(message, "INBOX")
    assert not message_has_label(message, "SENT")


def test_iter_history_message_ids():
    history = {
        "history": [
            {
                "messagesAdded": [
                    {"message": {"id": "a"}},
                    {"message": {"id": "b"}},
                ]
            },
            {"messagesAdded": [{"message": {"id": "c"}}]},
        ]
    }
    assert list(iter_history_message_ids(history)) == ["a", "b", "c"]


def test_build_reply_raw_includes_thread_headers():
    payload = GmailReplyPayload(body_text="Thanks for reaching out.")
    raw = build_reply_raw(
        to_email="customer@example.com",
        from_email="support@dental.com",
        subject="Appointment question",
        thread_id="thread456",
        in_reply_to="<incoming@example.com>",
        references="<incoming@example.com>",
        payload=payload,
    )
    assert raw
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    text = decoded.decode("utf-8")
    assert "To: customer@example.com" in text
    assert "Subject: Re: Appointment question" in text
    assert "In-Reply-To: <incoming@example.com>" in text
    assert "Thanks for reaching out." in text


def test_build_reply_raw_respects_subject_override():
    payload = GmailReplyPayload(
        body_text="Follow-up",
        subject="Custom subject",
    )
    raw = build_reply_raw(
        to_email="customer@example.com",
        from_email="support@dental.com",
        subject="Original",
        thread_id="thread456",
        in_reply_to="<incoming@example.com>",
        references="<incoming@example.com>",
        payload=payload,
    )
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    assert "Subject: Custom subject" in decoded
