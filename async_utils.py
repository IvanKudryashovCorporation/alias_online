"""
Async utilities for managing background tasks in Kivy.

Since Kivy does not support native async/await, we use Thread + Clock.schedule_once pattern.
This module encapsulates that pattern to avoid duplication.
"""

import logging
from threading import Thread
from typing import Any, Callable, Optional, TypeVar

from kivy.clock import Clock

logger = logging.getLogger(__name__)

# Type variables for generic callbacks
T = TypeVar("T")
E = TypeVar("E", bound=Exception)


def run_async(
    worker: Callable[[], T],
    on_success: Optional[Callable[[T], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_finally: Optional[Callable[[], None]] = None,
    daemon: bool = True,
) -> None:
    """
    Run a function in a background thread and schedule callbacks on completion.

    This is a helper to avoid repetition of Thread + Clock.schedule_once pattern
    throughout the codebase.

    Args:
        worker: Function to run in background thread. Should return a value or raise exception.
        on_success: Callback for successful completion. Called with the return value.
        on_error: Callback for exception. Called with the exception.
        on_finally: Callback to run after success or error (like finally block).
        daemon: If True, thread will not prevent application from exiting.

    Example:
        def fetch_data():
            return api.get_user()

        def on_success(user):
            self.display_user(user)

        def on_error(exc):
            logger.error(f"Failed to fetch user: {exc}")

        run_async(fetch_data, on_success, on_error)
    """

    def _thread_target() -> None:
        """Worker thread function."""
        result = None
        error = None

        try:
            result = worker()
        except Exception as e:
            logger.error(f"Worker function failed: {e}", exc_info=True)
            error = e

        # Schedule callbacks on main thread
        if error is not None and on_error is not None:
            Clock.schedule_once(lambda _dt: _safe_call(on_error, error), 0)
        elif error is None and on_success is not None:
            Clock.schedule_once(lambda _dt: _safe_call(on_success, result), 0)

        if on_finally is not None:
            Clock.schedule_once(lambda _dt: _safe_call(on_finally), 0)

    thread = Thread(target=_thread_target, daemon=daemon)
    thread.start()


def run_async_with_token(
    worker: Callable[[int], T],
    on_success: Optional[Callable[[int, T], None]] = None,
    on_error: Optional[Callable[[int, Exception], None]] = None,
    token_counter: Optional[list[int]] = None,
) -> int:
    """
    Run async task with a token to track which request completed.

    Useful when multiple async requests are in flight and you need to ignore
    responses from cancelled/superseded requests.

    Args:
        worker: Function to run, receives token as argument
        on_success: Callback (token, result)
        on_error: Callback (token, exception)
        token_counter: Optional mutable list [counter] to increment. If None, creates new.

    Returns:
        The token assigned to this request

    Example:
        token_counter = [0]
        token = run_async_with_token(
            lambda t: api.search(query, token=t),
            on_success=lambda t, results: self.display(results) if t == token_counter[0] else None,
            token_counter=token_counter
        )
    """
    if token_counter is None:
        token_counter = [0]

    token_counter[0] += 1
    current_token = token_counter[0]

    def _wrapped_worker() -> T:
        return worker(current_token)

    def _on_success(result: T) -> None:
        if on_success is not None:
            on_success(current_token, result)

    def _on_error(exc: Exception) -> None:
        if on_error is not None:
            on_error(current_token, exc)

    run_async(_wrapped_worker, on_success=_on_success, on_error=_on_error)
    return current_token


def _safe_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Call a function and log any exceptions."""
    try:
        fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"Callback failed: {fn.__name__}: {e}", exc_info=True)
