# Alias Online Global Server Setup

## 1) Deploy backend to Render

1. Open the repository in Render using Blueprint (`render.yaml` in root).
2. Deploy service `alias-online-room-server`.
3. Wait until `/health` is available:
   - `https://<your-render-url>/health`

## 2) Point APK to global backend

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

## 3) Verify global multiplayer

1. Install fresh APK on two different networks/devices.
2. Create public room on device A.
3. Join from device B via public list/code.
4. Confirm shared chat, scores, and room state.
