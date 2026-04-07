import json
import os
import secrets
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from .profile_store import EMAIL_PATTERN, get_profile_by_email, reset_profile_password, validate_registration_payload
from .room_hub import is_local_room_server_url, room_server_url

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_SSL_PORT = 465
DEFAULT_SENDER_EMAIL = "aliasgameonline@gmail.com"
DEFAULT_SMTP_APP_PASSWORD = ""
DEFAULT_SMTP_TIMEOUT_SECONDS = 20
DEFAULT_CODE_TTL_SECONDS = 10 * 60
DEFAULT_RESEND_COOLDOWN_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_REMOTE_TIMEOUT_SECONDS = 12

AUTH_SERVER_URL_ENV = "ALIAS_AUTH_SERVER_URL"
VERIFICATION_MODE_ENV = "ALIAS_EMAIL_VERIFICATION_MODE"
REMOTE_TIMEOUT_ENV = "ALIAS_AUTH_TIMEOUT_SECONDS"
REMOTE_API_PREFIX = "/api/auth"

_PENDING_LOCK = threading.Lock()
_PENDING_REGISTRATIONS = {}
_PENDING_PASSWORD_RESETS = {}
_DOTENV_LOADED = False


@dataclass
class PendingRegistration:
    session_id: str
    name: str
    email: str
    password: str
    bio: str | None
    avatar_path: str | None
    code: str
    expires_at: float
    resend_available_at: float
    attempts_left: int


@dataclass
class PendingPasswordReset:
    session_id: str
    email: str
    code: str
    expires_at: float
    resend_available_at: float
    attempts_left: int


def _ensure_env_loaded():
    """
    SECURITY: Do NOT load .env.local or runtime config files.
    All secrets must come from actual environment variables only (CI/CD, sys env).
    
    This method is kept for compatibility but is now a no-op to prevent
    accidental credential leakage from development config files.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "Email verification using environment variables only. "
        "Credentials must be set via CI/CD or system environment."
    )


def _safe_int_env(name, default):
    _ensure_env_loaded()
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _code_ttl_seconds():
    return _safe_int_env("ALIAS_EMAIL_CODE_TTL_SECONDS", DEFAULT_CODE_TTL_SECONDS)


def _resend_cooldown_seconds():
    return _safe_int_env("ALIAS_EMAIL_RESEND_COOLDOWN_SECONDS", DEFAULT_RESEND_COOLDOWN_SECONDS)


def _max_attempts():
    return _safe_int_env("ALIAS_EMAIL_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)


def _remote_timeout_seconds():
    return _safe_int_env(REMOTE_TIMEOUT_ENV, DEFAULT_REMOTE_TIMEOUT_SECONDS)


def _smtp_sender_email():
    _ensure_env_loaded()
    return (os.getenv("ALIAS_SMTP_EMAIL") or DEFAULT_SENDER_EMAIL).strip().lower()


def _smtp_app_password():
    _ensure_env_loaded()
    raw = (os.getenv("ALIAS_SMTP_APP_PASSWORD") or "").strip()
    if raw:
        return raw.replace(" ", "")
    return DEFAULT_SMTP_APP_PASSWORD


def _smtp_host():
    _ensure_env_loaded()
    return (os.getenv("ALIAS_SMTP_HOST") or DEFAULT_SMTP_HOST).strip()


def _smtp_port():
    return _safe_int_env("ALIAS_SMTP_PORT", DEFAULT_SMTP_PORT)


def _smtp_timeout_seconds():
    return _safe_int_env("ALIAS_SMTP_TIMEOUT_SECONDS", DEFAULT_SMTP_TIMEOUT_SECONDS)


def _smtp_tls_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _smtp_error_details(error):
    details = " ".join(str(error).strip().split())
    if not details:
        details = error.__class__.__name__
    if len(details) > 140:
        details = f"{details[:137]}..."
    return details


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _mask_email(email):
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return email
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _normalize_code(code):
    return "".join(character for character in (code or "") if character.isdigit())


def _is_mobile_platform():
    try:
        from kivy.utils import platform as kivy_platform
    except Exception:
        return False
    return kivy_platform in {"android", "ios"}


def _normalize_base_url(raw_url):
    clean_url = (raw_url or "").strip().rstrip("/")
    if not clean_url:
        return ""

    candidate = clean_url if "://" in clean_url else f"http://{clean_url}"
    parsed = urllib.parse.urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return ""

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return ""

    return f"{scheme}://{parsed.netloc}"


def _auth_server_base_url():
    _ensure_env_loaded()
    explicit = _normalize_base_url(os.getenv(AUTH_SERVER_URL_ENV))
    if explicit:
        return explicit
    return _normalize_base_url(room_server_url())


def _verification_mode():
    _ensure_env_loaded()
    return (os.getenv(VERIFICATION_MODE_ENV) or "").strip().lower()


def _can_use_local_email_verification():
    return bool(_smtp_app_password())


def _should_try_remote_verification():
    mode = _verification_mode()
    if mode in {"local", "offline", "disabled"}:
        return False
    if mode in {"remote", "server", "on"}:
        return True

    base_url = _auth_server_base_url()
    if not base_url:
        return False

    if _is_mobile_platform():
        if is_local_room_server_url(base_url) and _can_use_local_email_verification():
            return False
        return True

    return not is_local_room_server_url(base_url)


def _must_use_remote_verification():
    mode = _verification_mode()
    if mode in {"remote", "server", "on"}:
        return True
    if _is_mobile_platform():
        return not _can_use_local_email_verification()
    return False


def _ensure_mobile_global_auth_url():
    if not _is_mobile_platform():
        return

    mode = _verification_mode()
    if mode in {"local", "offline", "disabled", "remote", "server", "on"}:
        return

    if _can_use_local_email_verification():
        return

    base_url = _auth_server_base_url()
    if not base_url or is_local_room_server_url(base_url):
        raise ValueError(
            "Почтовая верификация для мобильной версии не настроена. Укажи публичный ALIAS_ROOM_SERVER_URL и перезапусти приложение."
        )


def _remote_request_json(method, path, payload=None):
    base_url = _auth_server_base_url()
    if not base_url:
        raise ConnectionError("Сервер подтверждения почты не настроен.")

    url = f"{base_url}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_remote_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        message = ""
        try:
            parsed = json.loads(details)
            if isinstance(parsed, dict):
                message = str(parsed.get("error") or "")
        except json.JSONDecodeError:
            message = ""
        raise ValueError(message or f"Ошибка сервера подтверждения ({error.code}).") from error
    except urllib.error.URLError as error:
        raise ConnectionError("Не удалось подключиться к серверу подтверждения почты. Проверь интернет и попробуй снова.") from error

    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError as error:
        raise ValueError("Сервер подтверждения вернул некорректный ответ.") from error

    return parsed if isinstance(parsed, dict) else {}


def _try_remote(path, *, method="POST", payload=None):
    remote_error = None
    if not _should_try_remote_verification():
        return None, remote_error

    try:
        result = _remote_request_json(method, path, payload=payload)
        return result, None
    except ValueError:
        # Server returned explicit business/validation error.
        raise
    except ConnectionError as error:
        remote_error = error
        if _must_use_remote_verification():
            raise ValueError(str(error)) from error
    return None, remote_error


def _cleanup_expired_locked(now=None):
    now = time.time() if now is None else now
    expired_keys = [session_id for session_id, record in _PENDING_REGISTRATIONS.items() if record.expires_at <= now]
    for session_id in expired_keys:
        _PENDING_REGISTRATIONS.pop(session_id, None)
    expired_reset_keys = [session_id for session_id, record in _PENDING_PASSWORD_RESETS.items() if record.expires_at <= now]
    for session_id in expired_reset_keys:
        _PENDING_PASSWORD_RESETS.pop(session_id, None)


def _send_code_email(recipient_email, code, subject=None, intro_line=None):
    sender_email = _smtp_sender_email()
    app_password = _smtp_app_password()
    if not app_password:
        raise ValueError(
            "Почтовая отправка не настроена. Укажи ALIAS_SMTP_APP_PASSWORD для аккаунта aliasgameonline@gmail.com."
        )

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = (subject or "").strip() or "Код подтверждения Alias Online"
    intro = (intro_line or "").strip() or f"Твой код подтверждения для Alias Online: {code}"
    message.set_content(
        "\n".join(
            [
                "Привет!",
                "",
                intro,
                "",
                f"Код действует {_code_ttl_seconds() // 60} минут.",
                "Если ты не запрашивал действие, просто проигнорируй это письмо.",
            ]
        )
    )

    context = _smtp_tls_context()
    smtp_host = _smtp_host()
    smtp_port = int(_smtp_port())
    smtp_timeout = max(5, int(_smtp_timeout_seconds()))

    attempts = []
    if smtp_port == DEFAULT_SMTP_SSL_PORT:
        attempts.append(("ssl", smtp_port))
        attempts.append(("starttls", DEFAULT_SMTP_PORT))
    else:
        attempts.append(("starttls", smtp_port))
        if smtp_port != DEFAULT_SMTP_SSL_PORT:
            attempts.append(("ssl", DEFAULT_SMTP_SSL_PORT))

    last_error = None
    for mode, port in attempts:
        try:
            if mode == "ssl":
                with smtplib.SMTP_SSL(smtp_host, int(port), timeout=smtp_timeout, context=context) as server:
                    server.login(sender_email, app_password)
                    server.send_message(message)
                    return

            with smtplib.SMTP(smtp_host, int(port), timeout=smtp_timeout) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(sender_email, app_password)
                server.send_message(message)
                return
        except smtplib.SMTPAuthenticationError as error:
            raise ValueError("Не удалось войти в почту отправителя. Проверь ALIAS_SMTP_EMAIL и ALIAS_SMTP_APP_PASSWORD.") from error
        except (smtplib.SMTPException, OSError, ssl.SSLError) as error:
            last_error = error
            continue

    details = _smtp_error_details(last_error) if last_error is not None else "неизвестная ошибка"
    raise ValueError(
        f"Не удалось отправить письмо с кодом. Проверь интернет и SMTP-настройки. Детали: {details}"
    )


def _local_begin_registration(payload, bio, avatar_path):
    now = time.time()
    session_id = secrets.token_urlsafe(24)
    code = _generate_code()
    record = PendingRegistration(
        session_id=session_id,
        name=payload["name"],
        email=payload["email"],
        password=payload["password"],
        bio=bio,
        avatar_path=avatar_path,
        code=code,
        expires_at=now + _code_ttl_seconds(),
        resend_available_at=now + _resend_cooldown_seconds(),
        attempts_left=_max_attempts(),
    )
    _send_code_email(record.email, record.code)

    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        for existing_id, existing_record in list(_PENDING_REGISTRATIONS.items()):
            if existing_record.email == record.email:
                _PENDING_REGISTRATIONS.pop(existing_id, None)
        _PENDING_REGISTRATIONS[record.session_id] = record

    return {
        "session_id": record.session_id,
        "masked_email": _mask_email(record.email),
        "expires_in": int(record.expires_at - now),
        "resend_in": int(record.resend_available_at - now),
    }


def _local_registration_state(session_id):
    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")
        return {
            "session_id": record.session_id,
            "masked_email": _mask_email(record.email),
            "expires_in": max(0, int(record.expires_at - now)),
            "resend_in": max(0, int(record.resend_available_at - now)),
            "attempts_left": max(0, int(record.attempts_left)),
        }


def _local_resend_registration(session_id):
    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")
        seconds_left = int(record.resend_available_at - now)
        if seconds_left > 0:
            raise ValueError(f"Повторная отправка будет доступна через {seconds_left} сек.")
        email = record.email

    new_code = _generate_code()
    _send_code_email(email, new_code)

    now = time.time()
    with _PENDING_LOCK:
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")
        record.code = new_code
        record.expires_at = now + _code_ttl_seconds()
        record.resend_available_at = now + _resend_cooldown_seconds()
        return {
            "session_id": record.session_id,
            "masked_email": _mask_email(record.email),
            "expires_in": int(record.expires_at - now),
            "resend_in": int(record.resend_available_at - now),
            "attempts_left": max(0, int(record.attempts_left)),
        }


def _local_confirm_registration(session_id, code):
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")
        if record.expires_at <= now:
            _PENDING_REGISTRATIONS.pop(session_id, None)
            raise ValueError("Срок действия кода истёк. Запроси новый код.")
        if normalized_code != record.code:
            record.attempts_left = max(0, record.attempts_left - 1)
            if record.attempts_left <= 0:
                _PENDING_REGISTRATIONS.pop(session_id, None)
                raise ValueError("Превышено число попыток. Начни регистрацию заново.")
            raise ValueError(f"Неверный код. Осталось попыток: {record.attempts_left}.")

        _PENDING_REGISTRATIONS.pop(session_id, None)
        return {
            "name": record.name,
            "email": record.email,
            "password": record.password,
            "bio": record.bio,
            "avatar_path": record.avatar_path,
        }


def _local_cancel_registration(session_id):
    with _PENDING_LOCK:
        _PENDING_REGISTRATIONS.pop(session_id, None)


def _local_begin_password_reset(clean_email):
    now = time.time()
    session_id = secrets.token_urlsafe(24)
    code = _generate_code()
    record = PendingPasswordReset(
        session_id=session_id,
        email=clean_email,
        code=code,
        expires_at=now + _code_ttl_seconds(),
        resend_available_at=now + _resend_cooldown_seconds(),
        attempts_left=_max_attempts(),
    )
    _send_code_email(
        record.email,
        record.code,
        subject="Код восстановления пароля Alias Online",
        intro_line=f"Твой код для восстановления пароля Alias Online: {record.code}",
    )

    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        for existing_id, existing_record in list(_PENDING_PASSWORD_RESETS.items()):
            if existing_record.email == record.email:
                _PENDING_PASSWORD_RESETS.pop(existing_id, None)
        _PENDING_PASSWORD_RESETS[record.session_id] = record

    return {
        "session_id": record.session_id,
        "masked_email": _mask_email(record.email),
        "expires_in": int(record.expires_at - now),
        "resend_in": int(record.resend_available_at - now),
    }


def _local_password_reset_state(session_id):
    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")
        return {
            "session_id": record.session_id,
            "masked_email": _mask_email(record.email),
            "expires_in": max(0, int(record.expires_at - now)),
            "resend_in": max(0, int(record.resend_available_at - now)),
            "attempts_left": max(0, int(record.attempts_left)),
        }


def _local_resend_password_reset(session_id):
    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")
        seconds_left = int(record.resend_available_at - now)
        if seconds_left > 0:
            raise ValueError(f"Повторная отправка будет доступна через {seconds_left} сек.")
        email = record.email

    new_code = _generate_code()
    _send_code_email(
        email,
        new_code,
        subject="Код восстановления пароля Alias Online",
        intro_line=f"Твой новый код для восстановления пароля Alias Online: {new_code}",
    )

    now = time.time()
    with _PENDING_LOCK:
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")
        record.code = new_code
        record.expires_at = now + _code_ttl_seconds()
        record.resend_available_at = now + _resend_cooldown_seconds()
        return {
            "session_id": record.session_id,
            "masked_email": _mask_email(record.email),
            "expires_in": int(record.expires_at - now),
            "resend_in": int(record.resend_available_at - now),
            "attempts_left": max(0, int(record.attempts_left)),
        }


def _local_confirm_password_reset(session_id, code):
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    now = time.time()
    with _PENDING_LOCK:
        _cleanup_expired_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")
        if record.expires_at <= now:
            _PENDING_PASSWORD_RESETS.pop(session_id, None)
            raise ValueError("Срок действия кода истёк. Запроси новый код.")
        if normalized_code != record.code:
            record.attempts_left = max(0, record.attempts_left - 1)
            if record.attempts_left <= 0:
                _PENDING_PASSWORD_RESETS.pop(session_id, None)
                raise ValueError("Превышено число попыток. Запроси код заново.")
            raise ValueError(f"Неверный код. Осталось попыток: {record.attempts_left}.")

        email = record.email
        _PENDING_PASSWORD_RESETS.pop(session_id, None)
        return email


def _local_cancel_password_reset(session_id):
    with _PENDING_LOCK:
        _PENDING_PASSWORD_RESETS.pop(session_id, None)


def begin_registration_verification(name, email, password, bio=None, avatar_path=None, db_path=None):
    _ensure_mobile_global_auth_url()

    payload = validate_registration_payload(
        name=name,
        email=email,
        password=password,
        db_path=db_path,
        allow_existing_email=False,
    )
    clean_bio = (bio or "").strip() or None
    clean_avatar_path = (avatar_path or "").strip() or None

    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/register/request-code",
        payload={
            "name": payload["name"],
            "email": payload["email"],
            "password": payload["password"],
            "bio": clean_bio,
            "avatar_path": clean_avatar_path,
        },
    )
    if remote_result is not None:
        return {
            "session_id": remote_result.get("session_id", ""),
            "masked_email": remote_result.get("masked_email", _mask_email(payload["email"])),
            "expires_in": int(remote_result.get("expires_in", _code_ttl_seconds())),
            "resend_in": int(remote_result.get("resend_in", _resend_cooldown_seconds())),
        }

    try:
        return _local_begin_registration(payload, clean_bio, clean_avatar_path)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise


def get_registration_verification_state(session_id):
    clean_session_id = (session_id or "").strip()
    if clean_session_id:
        encoded = urllib.parse.quote(clean_session_id, safe="")
        remote_result, _ = _try_remote(
            f"{REMOTE_API_PREFIX}/register/state?session_id={encoded}",
            method="GET",
        )
        if remote_result is not None:
            return {
                "session_id": remote_result.get("session_id", clean_session_id),
                "masked_email": remote_result.get("masked_email", ""),
                "expires_in": max(0, int(remote_result.get("expires_in", 0))),
                "resend_in": max(0, int(remote_result.get("resend_in", 0))),
                "attempts_left": max(0, int(remote_result.get("attempts_left", _max_attempts()))),
            }

    return _local_registration_state(clean_session_id)


def resend_registration_verification_code(session_id):
    clean_session_id = (session_id or "").strip()
    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/register/resend",
        payload={"session_id": clean_session_id},
    )
    if remote_result is not None:
        return {
            "session_id": remote_result.get("session_id", clean_session_id),
            "masked_email": remote_result.get("masked_email", ""),
            "expires_in": int(remote_result.get("expires_in", _code_ttl_seconds())),
            "resend_in": int(remote_result.get("resend_in", _resend_cooldown_seconds())),
            "attempts_left": max(0, int(remote_result.get("attempts_left", _max_attempts()))),
        }

    try:
        return _local_resend_registration(clean_session_id)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise


def confirm_registration_verification_code(session_id, code):
    clean_session_id = (session_id or "").strip()
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/register/confirm",
        payload={"session_id": clean_session_id, "code": normalized_code},
    )
    if remote_result is not None:
        return {
            "name": remote_result.get("name", ""),
            "email": remote_result.get("email", ""),
            "password": remote_result.get("password", ""),
            "bio": remote_result.get("bio"),
            "avatar_path": remote_result.get("avatar_path"),
        }

    try:
        return _local_confirm_registration(clean_session_id, normalized_code)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise


def cancel_registration_verification(session_id):
    clean_session_id = (session_id or "").strip()
    if clean_session_id:
        _try_remote(
            f"{REMOTE_API_PREFIX}/register/cancel",
            payload={"session_id": clean_session_id},
        )
    _local_cancel_registration(clean_session_id)


def begin_password_reset(email, db_path=None):
    _ensure_mobile_global_auth_url()

    clean_email = (email or "").strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    profile = get_profile_by_email(clean_email, db_path=db_path)
    if profile is None:
        raise ValueError("Аккаунт с таким e-mail не найден. Проверь адрес или создай новый аккаунт.")

    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/password/request-code",
        payload={"email": clean_email},
    )
    if remote_result is not None:
        return {
            "session_id": remote_result.get("session_id", ""),
            "masked_email": remote_result.get("masked_email", _mask_email(clean_email)),
            "expires_in": int(remote_result.get("expires_in", _code_ttl_seconds())),
            "resend_in": int(remote_result.get("resend_in", _resend_cooldown_seconds())),
        }

    try:
        return _local_begin_password_reset(clean_email)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise


def get_password_reset_state(session_id):
    clean_session_id = (session_id or "").strip()
    if clean_session_id:
        encoded = urllib.parse.quote(clean_session_id, safe="")
        remote_result, _ = _try_remote(
            f"{REMOTE_API_PREFIX}/password/state?session_id={encoded}",
            method="GET",
        )
        if remote_result is not None:
            return {
                "session_id": remote_result.get("session_id", clean_session_id),
                "masked_email": remote_result.get("masked_email", ""),
                "expires_in": max(0, int(remote_result.get("expires_in", 0))),
                "resend_in": max(0, int(remote_result.get("resend_in", 0))),
                "attempts_left": max(0, int(remote_result.get("attempts_left", _max_attempts()))),
            }

    return _local_password_reset_state(clean_session_id)


def resend_password_reset_code(session_id):
    clean_session_id = (session_id or "").strip()
    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/password/resend",
        payload={"session_id": clean_session_id},
    )
    if remote_result is not None:
        return {
            "session_id": remote_result.get("session_id", clean_session_id),
            "masked_email": remote_result.get("masked_email", ""),
            "expires_in": int(remote_result.get("expires_in", _code_ttl_seconds())),
            "resend_in": int(remote_result.get("resend_in", _resend_cooldown_seconds())),
            "attempts_left": max(0, int(remote_result.get("attempts_left", _max_attempts()))),
        }

    try:
        return _local_resend_password_reset(clean_session_id)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise


def confirm_password_reset_code(session_id, code, new_password, db_path=None):
    clean_session_id = (session_id or "").strip()
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    remote_result, remote_error = _try_remote(
        f"{REMOTE_API_PREFIX}/password/confirm",
        payload={"session_id": clean_session_id, "code": normalized_code},
    )
    if remote_result is not None:
        reset_email = (remote_result.get("email") or "").strip().lower()
        if not reset_email:
            raise ValueError("Сервер не вернул e-mail для завершения смены пароля.")
        return reset_profile_password(email=reset_email, new_password=new_password, db_path=db_path)

    try:
        reset_email = _local_confirm_password_reset(clean_session_id, normalized_code)
    except ValueError as local_error:
        if remote_error is not None:
            raise ValueError(str(remote_error)) from local_error
        raise

    return reset_profile_password(email=reset_email, new_password=new_password, db_path=db_path)


def cancel_password_reset(session_id):
    clean_session_id = (session_id or "").strip()
    if clean_session_id:
        _try_remote(
            f"{REMOTE_API_PREFIX}/password/cancel",
            payload={"session_id": clean_session_id},
        )
    _local_cancel_password_reset(clean_session_id)
