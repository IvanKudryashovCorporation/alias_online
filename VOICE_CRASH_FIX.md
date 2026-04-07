# 🔧 Исправление Краша Voice Polling

## 📋 Краткое резюме

**Проблема:** Приложение падает сразу после вывода лога "Starting voice polling for room..."

**Причина:** Неопределена (может быть audio, Clock, thread, или race condition)

**Решение:** Добавлено подробное логирование + безопасный контроллер

---

## 🚀 Как запустить исправления

### Шаг 1: Замени старый контроллер на новый безопасный

```bash
# Новый файл уже создан:
# controllers/voice_polling_controller_safe.py

# Он полностью заменяет старый контроллер
# с подробным логированием и защитой от ошибок
```

### Шаг 2: Проверь импорт в room_screen.py

Код уже обновлён, он автоматически использует новый безопасный контроллер.

### Шаг 3: Запусти с диагностикой

```bash
# Запуск с подробным логированием
python main.py 2>&1 | tee debug.log

# Создай комнату и посмотри на логи
# Последняя строка перед крашем покажет, где проблема
```

---

## 🔍 Что искать в логах

### Если видишь эту последовательность ✅

```
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice engine
[DEBUG  ] [RoomScreen.on_pre_enter] Voice engine started
[DEBUG  ] [RoomScreen.on_pre_enter] Preparing voice polling
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice polling controller
[INFO   ] [VoicePollingController.start_polling] Clock.schedule_interval SUCCESS
[INFO   ] [RoomScreen.on_pre_enter] Voice polling started successfully
[DEBUG  ] [RoomScreen.on_pre_enter] COMPLETED SUCCESSFULLY
```

**Результат:** ✅ Проблема РЕШЕНА! Приложение работает нормально

---

### Если видишь один из этих крашей ❌

**1. Crash в voice engine:**
```
[DEBUG  ] [RoomScreen.on_pre_enter] Starting voice engine
[ERROR  ] [RoomScreen.on_pre_enter] Voice engine FAILED
Traceback: ... (audio error)
```

**Решение:**
```bash
DISABLE_VOICE_AUDIO_INIT=true python main.py
```

Если это исправляет проблему — виновата audio subsystem.

---

**2. Crash в Clock.schedule_interval:**
```
[DEBUG  ] [VoicePollingController.start_polling] Scheduling interval: 1.00s
[ERROR  ] [VoicePollingController.start_polling] Clock.schedule_interval FAILED
Traceback: ...
```

**Решение:** Проверить `_poll_voice()` callback сигнатуру

---

**3. Crash в worker thread:**
```
[DEBUG  ] [VoicePollingController._poll_voice_impl] Spawning worker thread
[ERROR  ] [VoicePollingController._poll_voice_impl] Failed to spawn worker thread
Traceback: ...
```

**Решение:** Проверить `_poll_voice_worker()` код

---

**4. Crash в _finish_poll_voice:**
```
[ERROR  ] [VoicePollingController._finish_poll_voice] CRASHED
Traceback: ...
```

**Решение:** Это обработано безопасно, но видна ошибка в callback

---

## 📊 Файлы которые изменились

### ✅ Новые файлы:

1. **`controllers/voice_polling_controller_safe.py`** — NEW
   - Полностью переписанный контроллер с логированием
   - Каждая критическая операция залогирована
   - Все исключения обработаны и залогированы
   - Graceful degradation при ошибках

2. **`CRASH_DIAGNOSIS.md`** — NEW
   - Подробный guide по диагностике
   - 5 вероятных причин с решениями
   - Как различить типы ошибок

### ✏️ Обновленные файлы:

1. **`config.py`**
   - Добавлены флаги: `DISABLE_VOICE_AUDIO_INIT`, `VOICE_POLLING_DEBUG`

2. **`screens/room_screen.py`**
   - Добавлено подробное логирование в `on_pre_enter()`
   - Каждый этап обернут в try/except с логированием
   - Voice polling ошибки не падают, показывают warning

3. **`controllers/__init__.py`**
   - Экспорт нового контроллера

---

## 🧪 Процедура тестирования

### Test 1: Базовый запуск

```bash
python main.py
# 1. Создать комнату
# 2. Посмотреть на логи
# Ожидаемый результат: [RoomScreen.on_pre_enter] COMPLETED SUCCESSFULLY
```

### Test 2: Диагностика audio

```bash
DISABLE_VOICE_AUDIO_INIT=true python main.py
# 1. Создать комнату
# Ожидаемый результат:
# - Экран открывается нормально
# - Voice polling НЕ запускается (корректно)
# - Приложение продолжает работать
```

### Test 3: Повторный вход в комнату

```bash
python main.py
# 1. Создать комнату → войти
# 2. Выйти из комнаты
# 3. Войти в ту же комнату снова
# Ожидаемый результат: Нет краша, voice polling перезапускается
```

---

## 📈 Ожидаемые логи после исправления

После исправления в лог должны выводиться:

```
[INFO   ] [VoicePollingController] __init__ called
[INFO   ] [VoicePollingController] __init__ completed successfully
[INFO   ] [VoicePollingController.start_polling] ENTRY
[DEBUG  ] [VoicePollingController.start_polling] Stopping any existing poll event
[DEBUG  ] [VoicePollingController.start_polling] Resetting state
[DEBUG  ] [VoicePollingController.start_polling] Scheduling interval: 1.00s
[INFO   ] [VoicePollingController.start_polling] Clock.schedule_interval SUCCESS
[INFO   ] [VoicePollingController.start_polling] SUCCESS
[DEBUG  ] [VoicePollingController._poll_voice] Callback invoked (dt=1.0)
[DEBUG  ] [VoicePollingController._poll_voice_impl] Starting request (token=1, since_id=0)
[DEBUG  ] [VoicePollingController._poll_voice_impl] Spawning worker thread
[DEBUG  ] [VoicePollingController._poll_voice_impl] Worker thread started successfully
[DEBUG  ] [VoicePollingController._poll_voice_worker] Worker started (token=1)
[DEBUG  ] [VoicePollingController._poll_voice_worker] Calling get_room_voice_chunks
[DEBUG  ] [VoicePollingController._poll_voice_worker] Success: 0 chunks, last_id=0
[DEBUG  ] [VoicePollingController._poll_voice_worker] Scheduling callback
[DEBUG  ] [VoicePollingController._finish_poll_voice] ENTRY (token=1, status=success)
[DEBUG  ] [VoicePollingController._finish_poll_voice] Success: 0 chunks
[INFO   ] [VoicePollingController._reset_poll_backoff] Resetting 0 errors
```

**Ключевые точки:**
- ✅ `__init__ completed successfully`
- ✅ `Clock.schedule_interval SUCCESS`
- ✅ `Worker thread started successfully`
- ✅ `Worker started (token=N)`
- ✅ `_finish_poll_voice ENTRY`

---

## ⚠️ Что изменилось в поведении

### ДО (возможен краш)
```
voice_polling_controller.start_polling()
  ↓
Clock.schedule_interval(callback)
  ↓
callback → worker thread → ???
  ↓
CRASH (без логов, неясно где)
```

### ПОСЛЕ (безопасно)
```
voice_polling_controller.start_polling()
  ↓
[логирование каждого шага]
  ↓
Clock.schedule_interval(callback) [защищено в try/except]
  ↓
callback → [защищено в try/except]
  ↓
worker thread → [логирование каждого шага, все исключения обработаны]
  ↓
_finish_poll_voice → [обновление UI, все ошибки залогированы]
  ↓
✅ Всё видно в логах, нет скрытых ошибок
```

---

## 🔧 Fallback режимы

### Если audio не работает:
```bash
DISABLE_VOICE_AUDIO_INIT=true python main.py
```
Результат: Игра работает без голоса, но не падает

### Если voice polling не работает:
Приложение ловит ошибку и выводит warning:
```
self.status_label.text = "Ошибка голосового чата. Игра продолжает работать."
```

### Если worker thread падает:
```python
logger.error("[...] Worker thread crashed", exc_info=True)
# Polling продолжает работать, пытается заново
```

---

## 📞 Диагностический чек-лист

```
□ Запущено: python main.py
□ Посмотрены логи на последнюю строку перед крашем
□ Скопирована полная последовательность [VoicePollingController] логов
□ Если crash в audio → запущено DISABLE_VOICE_AUDIO_INIT=true
□ Если crash в Clock → проверена сигнатура _poll_voice(self, dt)
□ Если crash в worker → посмотрен traceback в логах
□ Проверено что [RoomScreen.on_pre_enter] COMPLETED SUCCESSFULLY выводится
```

---

## 🎯 Что дальше

**После запуска этого исправления:**

1. Посмотри на логи и определи точное место краша
2. Посмотри full traceback в `~/.kivy/logs/kivy_*.txt`
3. Используй DISABLE_VOICE_AUDIO_INIT=true для изоляции audio проблем
4. Если видно `[...] COMPLETED SUCCESSFULLY` → проблема РЕШЕНА ✅

---

## 📎 Полная диагностика

Для полного анализа смотри **`CRASH_DIAGNOSIS.md`**:
- 5 вероятных причин с вероятностью
- Как различить типы ошибок
- Как проверить каждую причину
- Как исправить каждую проблему
