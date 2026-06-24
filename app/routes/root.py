from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "whatsapp-slack-webhook",
        "wake": "/wake",
        "webhook": "/webhook",
        "slack_events": "/slack/events",
        "slack_interactions": "/slack/interactions",
    }


@router.get("/wake")
async def wake() -> dict[str, str]:
    return {"status": "ok"}
