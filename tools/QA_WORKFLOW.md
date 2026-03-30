# QA Workflow (Desktop + BlueStacks)

This project uses two smoke checks to validate changes before and after code edits.

## 1) Desktop smoke

Runs room lifecycle, game start, chat, scoring, host transfer, empty room cleanup, and profile friends query.

```powershell
python tools/qa_smoke_desktop.py
```

Optional:

```powershell
python tools/qa_smoke_desktop.py --room-port 8898
```

## 2) BlueStacks APK smoke

Launches the Android app in BlueStacks, captures screenshots at `t+8s` and `t+30s`, and collects logcat with critical error scan.

Without reinstall:

```powershell
powershell -ExecutionPolicy Bypass -File tools/qa_smoke_bluestacks.ps1
```

Install specific APK first:

```powershell
powershell -ExecutionPolicy Bypass -File tools/qa_smoke_bluestacks.ps1 -ApkPath "C:\path\to\aliasonline.apk"
```

Artifacts are saved into `logs/`:

- `apk_smoke_*.jpg` screenshots
- `apk_smoke_*.logcat.txt`
- `apk_smoke_*_summary.txt`
