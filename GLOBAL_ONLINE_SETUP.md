# Alias Online Global Server Setup

## 1) Deploy backend to Render

1. Open the repository in Render using Blueprint (`render.yaml` in root).
2. Deploy service `alias-online-room-server`.
3. Wait until `/health` is available:
   - `https://<your-render-url>/health`

## 2) Configure e-mail verification on server

In Render service environment variables, set:

- `ALIAS_SMTP_EMAIL=aliasgameonline@gmail.com`
- `ALIAS_SMTP_APP_PASSWORD=<Gmail app password>`
- `ALIAS_SMTP_HOST=smtp.gmail.com`
- `ALIAS_SMTP_PORT=587`

Without these variables, phone users will not receive registration/recovery codes.

Optional (for smarter voice-aware bots):

- `ALIAS_OPENAI_API_KEY=<your OpenAI API key>`
- `ALIAS_OPENAI_BASE_URL=https://api.openai.com/v1` (optional override)
- `ALIAS_OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe` (optional override)

When `ALIAS_OPENAI_API_KEY` is set, bots in active rounds can analyze recent explainer voice chunks and produce more context-aware guesses.

## 3) Point APK to global backend

Use one of these methods:

- Preferred for CI APK build:
  1. Add GitHub secret `ALIAS_ROOM_SERVER_URL`
  2. Value example: `https://alias-online-room-server.onrender.com`
  3. Run Android build workflow

- Local/manual:
  1. Put URL into `data/room_server_url.txt`
  2. Rebuild APK

Priority order in app:

1. `ALIAS_ROOM_SERVER_URL` env var
2. `room_server_url.txt` from app/user data
3. fallback local server `http://127.0.0.1:8765`

The same backend URL is also used for e-mail code verification API.

## 4) Verify global multiplayer + registration

1. Install fresh APK on two different networks/devices.
2. Create public room on device A.
3. Join from device B via public list/code.
4. Confirm shared chat, scores, and room state.
5. Register a new account and confirm that a 6-digit code arrives by e-mail.
