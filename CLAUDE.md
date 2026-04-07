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

### New (Post-Refactoring)
- **Client**: Kivy 2.3.1, Python 3.11, single-activity Android app. Entry point: `main.py`
- **Server**: `server/room_server.py` — `ThreadingHTTPServer` on Render (free tier, 10-20s cold start). SQLite DB at `/var/data/rooms.db`
- **Configuration**: `config.py` — ALL constants (sizes, timeouts, colors, API endpoints) configured here. Supports env vars with fallbacks.
- **Network/API**:
  - `api_client.py` — centralized HTTP client with retry logic, interceptors, unified error handling
  - `services/room_hub.py` — room API calls (using api_client)
  - Custom exceptions: `ApiError`, `ConnectionError`, `ValidationError`, `ServerError`
- **Async Utilities**: `async_utils.py` — `run_async()` wrapper for Thread + Clock.schedule_once pattern to avoid duplication
- **Logging**: `logging_config.py` — centralized logging setup, all modules use `logging.getLogger(__name__)`
- **UI framework**: Custom components in `ui/components.py`, theme/colors in `ui/theme.py`, feedback in `ui/feedback.py`
  - Screens refactored: `room_screen.py` split into mixins (state, voice, chat, layout) + thin main class
- **Screens**: `screens/` — each screen is a separate file. Large screens (CreateRoom, Registration, StartScreen) still need component breakdown.
- **Services**:
  - `services/room_hub.py` (room API client using api_client)
  - `services/profile_store.py` (local profile storage)
  - `services/email_verification.py` (email sending)
  - `services/voice_engine.py` (voice recording/playback)

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

## Configuration

All constants are centralized in `config.py`:
- **Sizes**: `BUTTON_COMPACT_WIDTH`, `BUTTON_NORMAL_HEIGHT`, `SPACING_MD`, `PADDING_LG`, etc.
- **Timing**: `POLLING_INTERVAL_SECONDS`, `COUNTDOWN_TIMER_INTERVAL`, `GAME_START_WATCHDOG_TIMEOUT`, etc.
- **Network**: `DEFAULT_LOCAL_ROOM_SERVER_URL`, `REMOTE_GET_ATTEMPTS`, `RETRYABLE_HTTP_STATUSES`, etc.
- **Game**: `ROOM_CREATION_COST`, `ROOM_EXIT_PENALTY_COINS`, `MESSAGE_HISTORY_MAX_SIZE`, etc.
- **Colors**: All 47 colors in `COLORS` dict
- **Env vars**: All constants support env var overrides (e.g., `POLLING_INTERVAL_SECONDS=1.0`, `DEBUG_MODE=true`)

To use: `from config import POLLING_INTERVAL_SECONDS, COLORS`

## Networking & API

### API Client Pattern
All HTTP requests go through `api_client.ApiClient`:
```python
from api_client import get_api_client, ConnectionError, ValidationError

client = get_api_client()
try:
    response = client.get("/api/endpoint", params={"key": "value"})
except ConnectionError as e:
    print(f"Network error: {e}")
except ValidationError as e:
    print(f"Bad request: {e}")
```

Features:
- Automatic retry with exponential backoff (configurable retryable statuses)
- Request/response interceptors for logging
- SSL verification fallback for mobile
- Unified exception types

### Async Pattern
Instead of `Thread + Clock.schedule_once`, use `run_async()`:
```python
from async_utils import run_async

def fetch_data():
    return api_client.get("/api/data")

def on_success(data):
    self.display_data(data)

def on_error(exc):
    logger.error(f"Failed: {exc}")

run_async(fetch_data, on_success, on_error)
```

### Logging
All modules use standard logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Message")
logger.error("Error", exc_info=True)
```

Call `logging_config.setup_logging()` at app startup (see main.py).

## Key Technical Patterns

### Network calls must be non-blocking (UPDATED)
Server has 10-20s cold start. Use `run_async()` for all network calls:
```python
def _do_action(self):
    run_async(self._worker, self._on_result, self._on_error)

def _worker(self):
    return room_hub.some_call()

def _on_result(self, result):
    self.update_ui(result)

def _on_error(self, exc):
    logger.error(f"Failed: {exc}")
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

## Refactoring Status

### Completed
✓ Centralized config.py with all constants
✓ ApiClient abstraction layer (api_client.py)
✓ Async utilities (async_utils.py) for run_async pattern
✓ Logging infrastructure (logging_config.py)
✓ Room screen split into mixins (state, voice, chat, layout)

### In Progress / TODO
- [ ] Replace all urllib.request calls in services/ with api_client
- [ ] Add type hints (typing) to all functions (goal: 100% coverage)
- [ ] Add docstrings to all public classes/functions
- [ ] Break down monolithic screens (CreateRoom 1056 lines, Registration 1109, StartScreen 797)
- [ ] Fix security: SSL_VERIFY fallback, remove console logging of sensitive data
- [ ] Optimize performance: defer canvas operations, increase polling interval to 1.0s
- [ ] Write unit tests: ApiClient, ValidationError, run_async, state versioning logic
- [ ] Update all error handling to use new exception types from api_client

### Anti-Patterns to Avoid
❌ Direct `urllib.request` calls — use ApiClient
❌ `Thread(...).start() + Clock.schedule_once(...)` duplication — use run_async()
❌ Magic numbers in code — use config.py
❌ `except: pass` or bare except — always log with exc_info=True
❌ No type hints on function signatures
❌ No docstrings on public methods
❌ Kivy widget creation in loops without signature check (perf issue)
