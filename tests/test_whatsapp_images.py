import httpx
import pytest

from app.agent.agent import build_instructions, create_whatsapp_agent
from app.whatsapp import client


def test_persona_is_design_guidelines_not_dental():
    text = build_instructions().lower()
    assert "design" in text
    assert "dental" not in text
    names = {t.name for t in create_whatsapp_agent(model="gpt-4o-mini").tools}
    assert "generate_and_send_image" in names
    assert "get_business_details" not in names


@pytest.mark.asyncio
async def test_upload_and_send_image(monkeypatch):
    monkeypatch.setattr(client, "WHATSAPP_ACCESS_TOKEN", "tok")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("content-type", "")))
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "MEDIA1"})
        body = request.content.decode()
        assert '"type":"image"' in body.replace(" ", "") and "MEDIA1" in body
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        mid = await client.upload_whatsapp_media(http, "PN", b"\xff\xd8jpeg", "image/jpeg")
        assert mid == "MEDIA1"
        assert await client.send_image_reply(http, "PN", "919", mid, "hi")
    assert seen[0][1].startswith("multipart/form-data")


@pytest.mark.asyncio
async def test_typing_indicator_payload(monkeypatch):
    monkeypatch.setattr(client, "WHATSAPP_ACCESS_TOKEN", "tok")
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode().replace(" ", ""))
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await client.send_typing_indicator(http, "PN", "wamid.X")
        assert not await client.send_typing_indicator(http, "PN", "")
    assert '"typing_indicator":{"type":"text"}' in bodies[0] and '"message_id":"wamid.X"' in bodies[0]
