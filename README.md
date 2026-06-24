# WhatsApp webhook (Render)

Minimal **FastAPI** service for the [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api): verify webhook, echo every incoming **text** message as `You typed: "<their message>"`, plus **`GET /wake`** to wake a sleeping [Render](https://render.com) instance.

## Endpoints

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/` | JSON with links to `/wake` and `/webhook` |
| `GET` | `/wake` | Fast 200 — use before testing WhatsApp on free/sleeping tiers |
| `GET` | `/webhook` | Meta subscription verification (`hub.mode`, `hub.verify_token`, `hub.challenge`) |
| `POST` | `/webhook` | Incoming WhatsApp events; for each incoming **text** message, replies `You typed: "<body>"` |

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in values
export $(grep -v '^#' .env | xargs)   # or set variables manually on Windows
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

VENV setup : 
```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

For Meta to reach your machine, expose HTTPS (e.g. [ngrok](https://ngrok.com)) and set the callback URL to `https://<public-host>/webhook`.

## Render.com

1. New **Web Service**, connect this repo.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables from [`.env.example`](.env.example) in the Render dashboard (use your real secrets, not the example file).
5. After deploy, open `https://<your-service>.onrender.com/wake` once so the dyno is warm before sending a WhatsApp message.
6. In **Meta Developer Console** → your app → **WhatsApp** → **Configuration**:
   - **Callback URL:** `https://<your-service>.onrender.com/webhook`
   - **Verify token:** same string as `VERIFY_TOKEN`
   - Subscribe to **`messages`** (and others only if you need them).

## Meta checklist

- WhatsApp product added to the app; **Phone number ID** and **access token** match `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN`.
- Optional: set **App Secret** as `WHATSAPP_APP_SECRET` so `POST /webhook` rejects requests without a valid `X-Hub-Signature-256`.

## Notes

- Replies only work inside the usual WhatsApp session window (e.g. user messaged you first). This demo does not send template messages.
- Temporary Meta tokens expire; use a long-lived or system user token for production.

## Gmail

The service can also monitor a business inbox and reply via the Gmail API + Pub/Sub push.

| Method | Path | Purpose |
|--------|------|--------|
| `POST` | `/gmail/push` | Pub/Sub push receiver for new mail notifications |
| `POST` | `/gmail/watch` | Register or renew Gmail watch (requires `X-Gmail-Watch-Secret` header) |

### Gmail setup

1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Gmail API**.
2. Create **OAuth 2.0 Desktop** credentials and set `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`.
3. Obtain a refresh token:

   ```bash
   GMAIL_CLIENT_ID=... GMAIL_CLIENT_SECRET=... python scripts/gmail_oauth_setup.py
   ```

   Paste the printed `GMAIL_REFRESH_TOKEN` into `.env` along with `GMAIL_MAILBOX_EMAIL`.
4. Create a **Pub/Sub topic** and a **push subscription** pointing to `https://<host>/gmail/push`.
5. Grant `gmail-api-push@system.gserviceaccount.com` the **Pub/Sub Publisher** role on the topic.
6. Set `GMAIL_PUBSUB_TOPIC` (e.g. `projects/my-project/topics/gmail-push`) and `GMAIL_PUSH_AUDIENCE` to your push URL.
7. After deploy, call `POST /gmail/watch` with header `X-Gmail-Watch-Secret: <GMAIL_WATCH_SECRET>`. Schedule this daily (watch expires in ~7 days).
