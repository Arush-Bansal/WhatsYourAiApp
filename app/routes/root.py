from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "whatsapp-webhook",
        "wake": "/wake",
        "webhook": "/webhook",
    }


@router.get("/wake")
async def wake() -> dict[str, str]:
    return {"status": "ok"}
