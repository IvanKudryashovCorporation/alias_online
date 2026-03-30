# Alias Online Flutter Client (Migration)

This folder is the migration lane for replacing the Kivy mobile client with Flutter while keeping the Python backend.

## Current state
- Flutter app scaffold created
- Unified dark game theme baseline
- Room API client scaffold added (`listPublicRooms`, `joinRoom`)
- Server URL wiring via Dart define: `ALIAS_ROOM_SERVER_URL`

## Run locally
```bash
cd flutter_client
flutter pub get
flutter run --dart-define=ALIAS_ROOM_SERVER_URL=https://<your-room-server>
```

## Next milestones
1. Auth screens + e-mail verification flow
2. Room creation/join UX
3. In-room game screen with score/chat/word cards
4. Voice transport integration with Python backend
5. Full parity checklist vs Kivy client
