"""
Centralized HTTP API client with retry logic, error handling, and request/response interceptors.
All network requests should go through this client.
"""

import json
import logging
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple, Union
from contextlib import suppress

import config

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body


class ConnectionError(ApiError):
    """Raised when network connection fails."""

    pass


class ValidationError(ApiError):
    """Raised when server returns 4xx error (client error)."""

    pass


class ServerError(ApiError):
    """Raised when server returns 5xx error."""

    pass


class ApiClient:
    """
    HTTP API client with automatic retry, error handling, and interceptors.

    Features:
    - Automatic retry with exponential backoff for retryable HTTP statuses
    - Request/response interceptors for logging and modification
    - Unified error handling with custom exception types
    - SSL certificate verification control via config
    """

    def __init__(
        self,
        base_url: str = config.DEFAULT_PUBLIC_ROOM_SERVER_URL,
        max_retries: int = config.REMOTE_GET_ATTEMPTS,
        timeout: float = config.REMOTE_WAKE_PROBE_TIMEOUT_SECONDS,
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL for API endpoints
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
        """
        self.base_url = self._normalize_url(base_url)
        self.max_retries = max_retries
        self.timeout = timeout
        self._request_interceptors: list[Callable[[Dict[str, Any]], None]] = []
        self._response_interceptors: list[Callable[[Dict[str, Any]], None]] = []

    def add_request_interceptor(self, interceptor: Callable[[Dict[str, Any]], None]) -> None:
        """Add a request interceptor."""
        self._request_interceptors.append(interceptor)

    def add_response_interceptor(self, interceptor: Callable[[Dict[str, Any]], None]) -> None:
        """Add a response interceptor."""
        self._response_interceptors.append(interceptor)

    def get(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Perform GET request with automatic retry.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            ConnectionError: On network failure
            ValidationError: On 4xx response
            ServerError: On 5xx response
        """
        url = self._build_url(endpoint, params)
        return self._request("GET", url, body=None, max_retries=config.REMOTE_GET_ATTEMPTS)

    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        is_mutation: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform POST request with automatic retry.

        Args:
            endpoint: API endpoint path
            data: JSON body to send
            is_mutation: If True, uses REMOTE_MUTATION_ATTEMPTS instead of GET attempts

        Returns:
            Parsed JSON response

        Raises:
            ConnectionError: On network failure
            ValidationError: On 4xx response
            ServerError: On 5xx response
        """
        url = self._build_url(endpoint)
        body = json.dumps(data or {}).encode("utf-8")
        max_retries = config.REMOTE_MUTATION_ATTEMPTS if is_mutation else config.REMOTE_GET_ATTEMPTS
        return self._request("POST", url, body=body, max_retries=max_retries)

    def _request(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Internal request method with retry logic."""
        attempt = 0
        last_error = None

        while attempt <= max_retries:
            try:
                # Build request
                request = urllib.request.Request(
                    url,
                    data=body,
                    method=method,
                    headers={"Content-Type": "application/json"},
                )

                # Request interceptors
                for interceptor in self._request_interceptors:
                    with suppress(Exception):
                        interceptor(
                            {
                                "method": method,
                                "url": url,
                                "body": body,
                                "attempt": attempt,
                            }
                        )

                # Execute request
                response = self._urlopen_with_fallback(request)

                # Parse response
                response_body = response.read().decode("utf-8")
                response_data = json.loads(response_body) if response_body else {}

                # Response interceptors
                for interceptor in self._response_interceptors:
                    with suppress(Exception):
                        interceptor(
                            {
                                "status": response.status,
                                "body": response_data,
                            }
                        )

                logger.debug(f"{method} {url} -> {response.status}")
                return response_data

            except urllib.error.HTTPError as e:
                status_code = e.code
                response_body = e.read().decode("utf-8") if hasattr(e, "read") else ""

                if status_code in config.RETRYABLE_HTTP_STATUSES and attempt < max_retries:
                    delay = self._retry_delay(attempt)
                    logger.warning(
                        f"{method} {url} -> {status_code}, retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue

                if 400 <= status_code < 500:
                    raise ValidationError(response_body or f"HTTP {status_code}", status_code, response_body)
                elif status_code >= 500:
                    raise ServerError(response_body or f"HTTP {status_code}", status_code, response_body)
                else:
                    raise ConnectionError(str(e))

            except urllib.error.URLError as e:
                if attempt < max_retries:
                    delay = self._retry_delay(attempt)
                    logger.warning(f"{method} {url} failed: {e}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    attempt += 1
                    continue
                last_error = e
                break

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from {method} {url}: {e}")
                raise ConnectionError(f"Invalid JSON response: {e}")

            except Exception as e:
                logger.error(f"Unexpected error in {method} {url}: {e}", exc_info=True)
                raise ConnectionError(f"Request failed: {e}")

        # All retries exhausted
        if last_error:
            raise ConnectionError(f"{method} {url} failed: {last_error}")
        raise ConnectionError(f"{method} {url} failed after {max_retries} retries")

    def _urlopen_with_fallback(self, request: urllib.request.Request) -> urllib.response.addinfourl:
        """Open URL with SSL verification fallback for mobile."""
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.URLError as e:
            # SSL fallback for mobile/Render: only on Render hosts + SSL error + flag explicitly enabled
            if (
                config.DISABLE_SSL_VERIFY
                and self._is_onrender_host(request.full_url)
                and self._looks_like_cert_error(e)
            ):
                logger.error(
                    f"INSECURE: SSL cert verification disabled for {request.full_url} "
                    f"(Render self-signed cert fallback). Error: {e}"
                )
                # Use ssl.create_default_context() with check_hostname=False for better compatibility
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                return urllib.request.urlopen(request, timeout=self.timeout, context=context)
            raise

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        index = max(1, int(attempt))
        base = config.REMOTE_RETRY_BASE_DELAY_SECONDS * (2 ** (index - 1))
        capped = min(base, 8.0)
        jitter = capped * (0.7 + 0.6 * random.random())
        return jitter

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL: strip whitespace and trailing slashes."""
        clean_url = (url or "").strip().rstrip("/")
        if not clean_url:
            return ""

        candidate = clean_url if "://" in clean_url else f"http://{clean_url}"
        parsed = urllib.parse.urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            return ""

        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return ""

        return f"{scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/")

    def _build_url(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> str:
        """Build full URL from endpoint and optional query parameters."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"
        return url

    @staticmethod
    def _is_onrender_host(url: str) -> bool:
        """Check if URL is hosted on Render."""
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").strip().lower()
        return host.endswith(".onrender.com")

    @staticmethod
    def _looks_like_cert_error(error: Exception) -> bool:
        """Check if error looks like SSL certificate issue."""
        chain = [error]
        reason = getattr(error, "reason", None)
        if reason is not None:
            chain.append(reason)

        for item in chain:
            if isinstance(item, ssl.SSLCertVerificationError):
                return True
            if isinstance(item, ssl.SSLError):
                text = str(item).lower()
                if "certificate" in text or "cert" in text:
                    return True

        error_text = str(error).lower()
        return "certificate verify failed" in error_text or "ssl: cert" in error_text


# Global client instance
_default_client: Optional[ApiClient] = None


def get_api_client(base_url: Optional[str] = None) -> ApiClient:
    """Get or create the default API client."""
    global _default_client
    if _default_client is None:
        _default_client = ApiClient(base_url or config.DEFAULT_PUBLIC_ROOM_SERVER_URL)
    return _default_client


def reset_api_client() -> None:
    """Reset the global API client (useful for testing)."""
    global _default_client
    _default_client = None
