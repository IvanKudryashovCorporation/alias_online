import time
from pathlib import Path

from kivy.core.audio import SoundLoader
from kivy.utils import platform

_LAST_HAPTIC_TS = 0.0
_HAPTIC_COOLDOWN_SEC = 0.07
_CLICK_SOUND = None


def _sound_path():
    return Path(__file__).resolve().parents[1] / "sounds" / "tap.wav"


def _load_click_sound():
    global _CLICK_SOUND
    if _CLICK_SOUND is not None:
        return _CLICK_SOUND

    sound_file = _sound_path()
    if not sound_file.exists():
        _CLICK_SOUND = False
        return None

    sound = SoundLoader.load(str(sound_file))
    if sound is None:
        _CLICK_SOUND = False
        return None

    sound.volume = 0.35
    _CLICK_SOUND = sound
    return sound


def _emit_haptic():
    global _LAST_HAPTIC_TS
    now = time.time()
    if now - _LAST_HAPTIC_TS < _HAPTIC_COOLDOWN_SEC:
        return
    _LAST_HAPTIC_TS = now

    if platform != "android":
        return

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        context = activity.getApplicationContext()
        Vibrator = autoclass("android.os.Vibrator")
        vibrator = context.getSystemService(context.VIBRATOR_SERVICE)
        if vibrator is None:
            return

        BuildVersion = autoclass("android.os.Build$VERSION")
        if int(BuildVersion.SDK_INT) >= 26:
            VibrationEffect = autoclass("android.os.VibrationEffect")
            effect = VibrationEffect.createOneShot(20, VibrationEffect.DEFAULT_AMPLITUDE)
            vibrator.vibrate(effect)
        else:
            vibrator.vibrate(20)
    except Exception:
        return


def trigger_tap_feedback(play_sound=True, haptic=True):
    if play_sound:
        sound = _load_click_sound()
        if sound:
            try:
                sound.stop()
                sound.play()
            except Exception:
                pass

    if haptic:
        _emit_haptic()
