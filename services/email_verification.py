import os
import secrets
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from .profile_store import EMAIL_PATTERN, get_profile_by_email, reset_profile_password, validate_registration_payload

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SENDER_EMAIL = "aliasgameonline@gmail.com"
DEFAULT_CODE_TTL_SECONDS = 10 * 60
DEFAULT_RESEND_COOLDOWN_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5

_PENDING_LOCK = threading.Lock()
_PENDING_REGISTRATIONS = {}
_PENDING_PASSWORD_RESETS = {}
_DOTENV_LOADED = False


def _ensure_env_loaded():
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    project_root = Path(__file__).resolve().parents[1]
    for file_name in (".env", ".env.local"):
        env_path = project_root / file_name
        if not env_path.exists():
            continue

        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        for line in lines:
            clean_line = line.strip()
            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue
            key, value = clean_line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue

            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            if key not in os.environ:
                os.environ[key] = value


@dataclass
class PendingRegistration:
    session_id: str
    name: str
    email: str
    password: str
    bio: str | None
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


def _smtp_sender_email():
    _ensure_env_loaded()
    return (os.getenv("ALIAS_SMTP_EMAIL") or DEFAULT_SENDER_EMAIL).strip().lower()


def _smtp_app_password():
    _ensure_env_loaded()
    raw = (os.getenv("ALIAS_SMTP_APP_PASSWORD") or "").strip()
    return raw.replace(" ", "")


def _smtp_host():
    _ensure_env_loaded()
    return (os.getenv("ALIAS_SMTP_HOST") or DEFAULT_SMTP_HOST).strip()


def _smtp_port():
    return _safe_int_env("ALIAS_SMTP_PORT", DEFAULT_SMTP_PORT)


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
            "Почтовая отправка не настроена. Укажи ALIAS_SMTP_APP_PASSWORD "
            "для аккаунта aliasgameonline@gmail.com."
        )

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient_email
    mail_subject = (subject or "").strip() or "Код подтверждения Alias Online"
    intro = (intro_line or "").strip() or f"Твой код подтверждения для Alias Online: {code}"
    message["Subject"] = mail_subject
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

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(_smtp_host(), _smtp_port(), timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, app_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise ValueError(
            "Не удалось войти в почту отправителя. Проверь ALIAS_SMTP_EMAIL и ALIAS_SMTP_APP_PASSWORD."
        ) from error
    except OSError as error:
        raise ValueError("Не удалось отправить письмо с кодом. Проверь интернет и SMTP-настройки.") from error


def begin_registration_verification(name, email, password, bio=None, db_path=None):
    payload = validate_registration_payload(
        name=name,
        email=email,
        password=password,
        db_path=db_path,
        allow_existing_email=False,
    )

    now = time.time()
    session_id = secrets.token_urlsafe(24)
    code = _generate_code()
    record = PendingRegistration(
        session_id=session_id,
        name=payload["name"],
        email=payload["email"],
        password=payload["password"],
        bio=(bio or "").strip() or None,
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


def get_registration_verification_state(session_id):
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


def resend_registration_verification_code(session_id):
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


def confirm_registration_verification_code(session_id, code):
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
        }


def cancel_registration_verification(session_id):
    with _PENDING_LOCK:
        _PENDING_REGISTRATIONS.pop(session_id, None)


def begin_password_reset(email, db_path=None):
    clean_email = (email or "").strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    profile = get_profile_by_email(clean_email, db_path=db_path)
    if profile is None:
        raise ValueError("Аккаунт с таким e-mail не найден. Проверь адрес или создай новый аккаунт.")

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


def get_password_reset_state(session_id):
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


def resend_password_reset_code(session_id):
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


def confirm_password_reset_code(session_id, code, new_password, db_path=None):
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

    return reset_profile_password(email=email, new_password=new_password, db_path=db_path)


def cancel_password_reset(session_id):
    with _PENDING_LOCK:
        _PENDING_PASSWORD_RESETS.pop(session_id, None)
