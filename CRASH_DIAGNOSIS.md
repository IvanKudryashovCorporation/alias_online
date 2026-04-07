# 🔍 Диагностика Краша при Voice Polling

## Логи, которые должны помочь локализовать проблему

При запуске теперь должны выводиться логи вида:

```
[DEBUG  ] [RoomScreen.on_pre_enter] Starting state polling
[DEBUG  ] [RoomScreen.on_pre_enter] State polling started
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice UI sync
[DEBUG  ] [RoomScreen.on_pre_enter] Voice UI sync started
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice engine
[DEBUG  ] [RoomScreen.on_pre_enter] Voice engine started
[DEBUG  ] [RoomScreen.on_pre_enter] Preparing voice polling
[DEBUG  ] [RoomScreen.on_pre_enter] room_code=Y7DKE3, player_name=Гость3020, client_id=...
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice polling controller
[INFO   ] [VoicePollingController] __init__ called
[INFO   ] [VoicePollingController] __init__ completed successfully
[INFO   ] [VoicePollingController.start_polling] ENTRY
[DEBUG  ] [VoicePollingController.start_polling] Stopping any existing poll event
[DEBUG  ] [VoicePollingController.start_polling] Resetting state
[DEBUG  ] [VoicePollingController.start_polling] Scheduling interval: 1.00s
[INFO   ] [VoicePollingController.start_polling] Clock.schedule_interval SUCCESS
[INFO   ] [VoicePollingController.start_polling] SUCCESS
[INFO   ] [RoomScreen.on_pre_enter] Voice polling started successfully
[DEBUG  ] [RoomScreen.on_pre_enter] COMPLETED SUCCESSFULLY
```

**Если видишь иную последнюю строку перед крашем — это сигнал нужного места.**

---

## 📋 Вероятные причины краша (в порядке вероятности)

### 1. **[ВЕРОЯТНОСТЬ: 40%] Audio subsystem crash при инициализации RoomVoiceEngine**

**Где проверить:**
- Строка в логе: `[DEBUG] [RoomScreen.on_pre_enter] Starting voice engine`
- Если после неё НЕТ: `[DEBUG] [RoomScreen.on_pre_enter] Voice engine started`

**Почему это может быть:**
- `sounddevice` не инициализировался на первый раз
- Микрофон не доступен на этом устройстве
- Ошибка при открытии audio streams (permission, device busy)
- Native/C library crash в sounddevice

**Как проверить:**
```bash
# Отключить audio инициализацию:
DISABLE_VOICE_AUDIO_INIT=true python main.py

# Если краш исчезнет - проблема в audio subsystem
```

**Исправление:**
```python
# Добавлена защита в voice_engine.py при инициализации
try:
    self._input_stream = sd.InputStream(...)
    self._input_stream.start()
except Exception as e:
    logger.error(f"Failed to initialize audio: {e}", exc_info=True)
    self.available = False  # Mark audio as unavailable
    return  # Don't crash
```

---

### 2. **[ВЕРОЯТНОСТЬ: 30%] Clock.schedule_interval callback error**

**Где проверить:**
- Строка в логе: `[DEBUG] [VoicePollingController.start_polling] Scheduling interval`
- Если после неё НЕТ: `[INFO] [VoicePollingController.start_polling] Clock.schedule_interval SUCCESS`

**Почему это может быть:**
- Callback `_poll_voice` имеет неправильную сигнатуру
- Callback выбросил исключение на первый вызов
- Kivy Clock механизм упал по неизвестной причине

**Как проверить:**
```python
# Временно заменить callback на пустую функцию:
def dummy_callback(dt):
    logger.debug("Dummy callback")
    return True

self._poll_event = Clock.schedule_interval(dummy_callback, 1.0)
# Если это работает - проблема в _poll_voice()
```

**Исправление:**
```python
# _poll_voice() теперь заёрнут в try/except:
def _poll_voice(self, dt=None):
    try:
        logger.debug(f"[VoicePollingController._poll_voice] Callback invoked")
        return self._poll_voice_impl(dt)
    except Exception as e:
        logger.error(f"Clock callback CRASHED: {e}", exc_info=True)
        return False  # Stop polling
```

---

### 3. **[ВЕРОЯТНОСТЬ: 15%] Thread creation или worker spawn error**

**Где проверить:**
- Строка в логе: `[DEBUG] [VoicePollingController._poll_voice_impl] Spawning worker thread`
- Если после неё НЕТ: `[DEBUG] [VoicePollingController._poll_voice_impl] Worker thread started successfully`

**Почему это может быть:**
- `Thread()` не смог создать thread (ОС limit, memory)
- `thread.start()` упал
- Daemon thread моментально упал из-за исключения

**Как проверить:**
```python
import threading
print(f"Active threads: {threading.active_count()}")
print(f"Max threads: {threading.stack_size()}")
# Если число threads растёт - утечка потоков
```

**Исправление:**
```python
try:
    thread = Thread(target=self._poll_voice_worker, ..., daemon=True)
    thread.start()
    logger.debug("Worker thread started")
except Exception as e:
    logger.error(f"Failed to spawn worker: {e}", exc_info=True)
    # Gracefully handle thread creation error
```

---

### 4. **[ВЕРОЯТНОСТЬ: 10%] Race condition в start_polling()**

**Где проверить:**
- Двойной запуск `on_pre_enter()` при быстром переключении экранов
- Логи показывают `[VoicePollingController.start_polling] Already active, stopping first`

**Почему это может быть:**
- Пользователь быстро входит/выходит из комнаты
- `stop_polling()` не отменил event на время
- Два потока одновременно вызвали `start_polling()`

**Как проверить:**
```python
# Добавлена защита:
if self._is_polling_active:
    logger.warning("Already active, stopping first")
    self.stop_polling()
```

**Исправление:**
Уже реализовано в новом контроллере через флаг `_is_polling_active`.

---

### 5. **[ВЕРОЯТНОСТЬ: 5%] RoomVoiceEngine.queue_remote_chunks() crash**

**Где проверить:**
- Строка в логе: `[DEBUG] [VoicePollingController._finish_poll_voice] Queuing for playback`
- Если после неё НЕТ успешного завершения

**Почему это может быть:**
- Voice engine не инициализировалась
- `_play_queue` переполнена или невалидна
- Ошибка при audio resampling

**Как проверить:**
```python
# Добавлена защита:
try:
    self.voice_engine.queue_remote_chunks(chunks)
except Exception as e:
    logger.error(f"Error queueing chunks: {e}", exc_info=True)
    # Continue without crashing
```

---

## 🔧 Как запустить диагностику

### Шаг 1: Включить подробное логирование

```bash
# Запустить с максимальным логированием
VOICE_POLLING_DEBUG=true python main.py
```

### Шаг 2: Отключить audio (если проблема в audio subsystem)

```bash
# Запустить БЕЗ audio инициализации
DISABLE_VOICE_AUDIO_INIT=true python main.py
```

**Если краш исчезнет:** Проблема в audio subsystem (причина #1)

### Шаг 3: Проверить временные логи

Смотреть на последнюю успешную строку перед крашем:

- Если `[RoomScreen.on_pre_enter] Starting voice engine` → проблема в audio
- Если `[VoicePollingController.start_polling] Scheduling interval` → проблема в Clock.schedule_interval
- Если `[VoicePollingController._poll_voice_impl] Spawning worker thread` → проблема в Thread
- Если `[VoicePollingController._poll_voice_impl] Worker thread started` → проблема в worker thread

### Шаг 4: Посмотреть полный traceback

В файле логов `~/.kivy/logs/kivy_*.txt` должен быть полный traceback.

---

## 📊 Различие типов ошибок по логам

### Python Exception (Error в thread)
```
[ERROR  ] [VoicePollingController._poll_voice_worker] UNEXPECTED ERROR: <error>
Traceback (most recent call last):
  File "...", line XX, in _poll_voice_worker
    ...
```

**Признак:** Видно строку с `[ERROR]` и `Traceback`

### Kivy Callback Crash (Error в Clock.schedule_interval)
```
[ERROR  ] [VoicePollingController._poll_voice] Clock callback CRASHED: <error>
Traceback (most recent call last):
  File "...", line XX, in _poll_voice
    ...
```

**Признак:** Видно `Clock callback CRASHED`

### Thread Crash (Error в worker потоке)
```
[ERROR  ] [VoicePollingController._poll_voice_worker] UNEXPECTED ERROR: <error>
[ERROR  ] Worker thread exited abnormally
```

**Признак:** Worker thread не вернул callback

### Native/Audio Crash (Crash в sounddevice C library)
```
[ERROR  ] [RoomScreen.on_pre_enter] Voice engine FAILED
Traceback (most recent call last):
  File ".../voice_engine.py", line XX, in start
    self._input_stream = sd.InputStream(...)
RuntimeError: [PortAudio error code] ...
```

**Признак:** Error из `sounddevice` или `PortAudio`

---

## 🚀 Как запустить и что смотреть

```bash
# 1. Стандартный запуск
python main.py

# 2. Создать комнату
# 3. Посмотреть логи на последнюю успешную строку

# Если видно: "[RoomScreen.on_pre_enter] COMPLETED SUCCESSFULLY"
# ✅ Проблема РЕШЕНА!

# Если видно: "[RoomScreen.on_pre_enter] Voice engine FAILED"
# ❌ Проблема в audio subsystem, запустить:
DISABLE_VOICE_AUDIO_INIT=true python main.py
```

---

## 📝 Контрольный список диагностики

```
□ Запущено с логированием: VOICE_POLLING_DEBUG=true
□ Посмотрены логи на последнюю успешную строку
□ Скопирован полный traceback из ~/.kivy/logs/kivy_*.txt
□ Проверено DISABLE_VOICE_AUDIO_INIT=true (если проблема в audio)
□ Проверено количество active threads
□ Проверена версия sounddevice: `python -c "import sounddevice; print(sounddevice.__version__)"`
□ Проверена версия Kivy: `python -c "import kivy; print(kivy.__version__)"`
```

---

## 🔐 Fallback режимы

### Если audio не работает (DISABLE_VOICE_AUDIO_INIT=true)

```python
# Игра работает без микрофона
# - Экран комнаты открывается ✅
# - Chat работает ✅
# - Состояние игры работает ✅
# - Микрофон/Voice не работает ❌ (но игра не падает)
```

### Если voice polling не работает

```python
# Игра продолжает работать
# - Состояние комнаты обновляется через state polling ✅
# - Chat работает ✅
# - Микрофон работает локально ✅
# - Удаленный голос не приходит ❌ (но игра не падает)
```

---

## 🎯 Следующие шаги после диагностики

1. **Если проблема в audio:** Исправь в `services/voice_engine.py`
2. **Если проблема в Clock:** Проверь сигнатуру `_poll_voice(self, dt)`
3. **Если проблема в Thread:** Убедись в исключениях в worker
4. **Если проблема в queue_remote_chunks:** Добавь больше логирования

---

## 📞 Если нужна помощь

Собери следующую информацию:

1. Последняя строка логов перед крашем
2. Full traceback из `~/.kivy/logs/kivy_*.txt`
3. Output от: `DISABLE_VOICE_AUDIO_INIT=true python main.py`
4. Output от: `python -c "import sounddevice; print(sounddevice.query_devices())"`
5. OS версия и Python версия
