# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is this
Multiplayer word-guessing game (like Alias/Taboo). Kivy 2.3.1 mobile app (Android APK via Buildozer) + Python HTTP server on Render.

## Build & Deploy Commands
- **Local run**: `python main.py` (desktop mode)
- **Server local**: `python server/room_server.py --host 0.0.0.0 --port 8765`
- **Lint**: `flake8 server/ services/ screens/ ui/ tests/ --select=E9,F63,F7,F82 --show-source --statistics`
- **Tests**: `python -m unittest discover -s tests -v`
- **Single test**: `python -m unittest tests.test_server_logic.TestClassName.test_method -v`
- **APK**: GitHub Actions builds APK on push to `main` (`.github/workflows/android-apk.yml`)
- **Server deploy**: Auto-deploys to Render on push (`render.yaml`)

## Architecture
- **Client**: Kivy 2.3.1, Python 3.11, single-activity Android app. Entry point: `main.py`
- **Server**: `server/room_server.py` — `ThreadingHTTPServer` on Render (free tier, 10-20s cold start). SQLite DB at `/var/data/rooms.db`
- **Network**: `services/room_hub.py` — HTTP client using `urllib.request`. Raises `ConnectionError` / `ValueError` only. Exponential backoff with retry for 408/425/429/5xx
- **UI framework**: Custom components in `ui/components.py`, theme/colors in `ui/theme.py`, feedback toasts in `ui/feedback.py`
- **Screens**: `screens/` — each screen is a separate file. `room_screen.py` is the largest (~2700+ lines)
- **Services**: `services/room_hub.py` (room API client), `services/profile_store.py` (local profile), `services/email_verification.py`, `services/voice_engine.py`

## Core Design Principle: Server Authority

**Server is the ONLY source of truth. Client NEVER invents state.**

- Server owns: rooms, players, roles, game state, scoring
- Client: renders UI, sends actions, applies server state
- After ANY event (join, leave, start, host change, round update) → server sends updated state → all clients must match
- State must be correct immediately after join — no temporary wrong UI, no waiting for polling
- No client-side role logic or state invention

## Game Model

### Rooms & Players
- Room: `room_id`, `players[]`, `host_id`, `explainer_id`, `game_state` (lobby | playing), `join_order`
- Player: `player_id`, `name`, `role` (explainer | guesser)

### Roles
- Host = explainer (only 1 explainer at a time)
- All others = guessers
- Explainer sees word, cannot send chat
- Guessers cannot see word, can send chat

### Game Flow
1. Host creates room → becomes explainer
2. Players join → guessers
3. Host starts game (server validated)
4. Round: explainer sees word, guessers guess in chat, correct guess → +5 AC guesser, +3 AC explainer → next word

### Host Transfer
- If host leaves: new host = lowest `join_order`, becomes explainer
- If no players remain: delete room

### UI State Rules
- Lobby: correct player list, correct roles, only host sees "Start", others see "Waiting"
- Game: explainer sees word, guessers see chat, only guessers can send messages

## Key Technical Patterns

### Network calls must be non-blocking
Server has 10-20s cold start. ALL network calls from UI must run in background `Thread`, with callback via `Clock.schedule_once` to return to main thread:
```python
def _do_action(self):
    Thread(target=self._worker, daemon=True).start()
def _worker(self):
    result = room_hub.some_call()
    Clock.schedule_once(lambda dt: self._on_result(result))
```

### Android text input bug (recurring)
After Android keyboard dismissal, Kivy/IME resets `foreground_color` to white, making text invisible on white background. Fix: `on_foreground_color` property interceptor in `AppTextInput` + scheduled color guard delays. If this comes up again, the interceptor approach is the right one.

### Touch handling with disabled widgets
`disabled=True` on Kivy widgets CONSUMES touches without dispatching them. This breaks button presses underneath. Use `TouchPassthroughFloatLayout` (returns False on touch events when disabled/hidden) for overlays. `LoadingOverlay` has its own `_is_interactive()` pattern.

### Layout centering
Invisible widgets with fixed `width` still occupy BoxLayout space. Set `width=dp(0)` on hidden siblings to keep visible widgets centered.

### Status/error labels
Labels used for error messages must have `opacity=1` and non-zero `height` when showing messages, otherwise feedback is silently discarded. Use `_show_status()` pattern.

## Server API
- Base URL configured in `services/room_hub.py` (auto-detects local vs Render)
- Rooms: create, join, leave, start-game, chat
- Auth: email verification, login, registration
- Rate limiting is implemented server-side
- Secret `ALIAS_ROOM_SERVER_URL` injected at APK build time via `data/room_server_url.txt`

## Language
- UI text is in Russian
- Code (variables, comments, commits) in English
- User communication: respond in the language the user uses (usually Russian)
