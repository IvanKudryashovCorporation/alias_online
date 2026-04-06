# Alias Online - Project Context

## What is this
Multiplayer word-guessing game (like Alias/Taboo). Kivy 2.3.1 mobile app (Android APK via Buildozer) + Python HTTP server on Render.

## Architecture
- **Client**: Kivy 2.3.1, Python 3.11, single-activity Android app. Entry point: `main.py`
- **Server**: `server/room_server.py` — HTTP server on Render (free tier, 10-20s cold start). SQLite DB at `/var/data/rooms.db`
- **Network**: `services/room_hub.py` — HTTP client using `urllib.request`. Raises `ConnectionError` / `ValueError` only
- **UI framework**: Custom components in `ui/components.py`, theme/colors in `ui/theme.py`
- **Screens**: `screens/` — each screen is a separate file. `room_screen.py` is the largest (~2700+ lines)

## Key technical patterns

### Android text input bug (recurring)
After Android keyboard dismissal, Kivy/IME resets `foreground_color` to white, making text invisible on white background. Fix: `on_foreground_color` property interceptor in `AppTextInput` + scheduled color guard delays. If this comes up again, the interceptor approach is the right one.

### Touch handling with disabled widgets
`disabled=True` on Kivy widgets CONSUMES touches without dispatching them. This breaks button presses underneath. Use `TouchPassthroughFloatLayout` (returns False on touch events when disabled/hidden) for overlays. LoadingOverlay has its own `_is_interactive()` pattern.

### Network calls must be non-blocking
Server has 10-20s cold start. ALL network calls from UI must run in background `Thread`, with callback via `Clock.schedule_once` to return to main thread. Pattern:
```python
def _do_action(self):
    Thread(target=self._worker, daemon=True).start()
def _worker(self):
    result = room_hub.some_call()
    Clock.schedule_once(lambda dt: self._on_result(result))
```

### Layout centering
Invisible widgets with fixed `width` still occupy BoxLayout space. Set `width=dp(0)` on hidden siblings to keep visible widgets centered.

### Status/error labels
Labels used for error messages must have `opacity=1` and non-zero `height` when showing messages, otherwise feedback is silently discarded. Use `_show_status()` pattern.

## Build & Deploy
- **APK**: GitHub Actions builds APK on push to `main`. Workflow in `.github/workflows/`
- **Server**: Auto-deploys to Render on push (see `render.yaml`)
- **Local run**: `python main.py` (desktop mode)
- **Lint**: `flake8` in CI
- **Tests**: Unit tests run in CI on PRs

## Server API
- Base URL configured in `services/room_hub.py`
- Rooms: create, join, leave, start-game, chat
- Auth: email verification, login, registration
- Rate limiting is implemented server-side

## Language
- UI text is in Russian
- Code (variables, comments, commits) in English
- User communication: respond in the language the user uses (usually Russian)
