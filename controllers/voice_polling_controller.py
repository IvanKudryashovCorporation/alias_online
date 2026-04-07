"""Voice chunks polling and synchronization."""

import config
import logging
import time
from threading import Thread, Lock
from kivy.clock import Clock
from services import get_room_voice_chunks

logger = logging.getLogger(__name__)


class VoicePollingController:
    """Manages voice chunk fetching via polling with safe concurrency controls."""

    def __init__(self, voice_engine):
        """Initialize voice polling controller.

        Args:
            voice_engine: RoomVoiceEngine instance for playing voice
        """
        self.voice_engine = voice_engine
        self._poll_event = None
        self._poll_lock = Lock()  # Protects polling state
        self._poll_in_flight = False
        self._poll_token = 0
        self._poll_started_at = 0.0
        self._poll_current_interval = config.POLLING_INTERVAL_SECONDS
        self._poll_consecutive_errors = 0
        self._last_voice_id = 0
        self._room_code = ""
        self._player_name = ""
        self._client_id = ""

    def start_polling(self, room_code: str, player_name: str, client_id: str = ""):
        """Start periodic voice chunk polling.

        Args:
            room_code: Room code for polling
            player_name: Player name for polling
            client_id: Optional client ID
        """
        self.stop_polling()
        self._room_code = (room_code or "").strip().upper()
        self._player_name = (player_name or "").strip()
        self._client_id = (client_id or "").strip()
        self._last_voice_id = 0
        self._poll_current_interval = config.POLLING_INTERVAL_SECONDS
        self._poll_consecutive_errors = 0
        self._poll_token = 0

        if self._room_code and self._player_name:
            logger.info(f"Starting voice polling for room {self._room_code}, player {self._player_name}")
            self._poll_event = Clock.schedule_interval(
                lambda _dt: self._poll_voice(),
                self._poll_current_interval
            )

    def stop_polling(self):
        """Stop voice chunk polling."""
        if self._poll_event is not None:
            logger.info("Stopping voice polling")
            self._poll_event.cancel()
            self._poll_event = None

    def _apply_poll_backoff(self):
        """Increase polling interval after error for exponential backoff."""
        self._poll_consecutive_errors += 1
        new_interval = config.POLLING_INTERVAL_SECONDS * (
            config.POLLING_ERROR_BACKOFF_FACTOR ** self._poll_consecutive_errors
        )
        self._poll_current_interval = min(new_interval, config.POLLING_MAX_BACKOFF_SECONDS)
        logger.warning(
            f"Voice poll error #{self._poll_consecutive_errors}, "
            f"backoff interval to {self._poll_current_interval:.2f}s"
        )
        self._reschedule_polling()

    def _reset_poll_backoff(self):
        """Reset polling interval after successful poll."""
        if self._poll_consecutive_errors > 0:
            logger.info(
                f"Voice poll success, resetting backoff from {self._poll_current_interval:.2f}s "
                f"to {config.POLLING_INTERVAL_SECONDS:.2f}s"
            )
            self._poll_consecutive_errors = 0
            self._poll_current_interval = config.POLLING_INTERVAL_SECONDS
            self._reschedule_polling()

    def _reschedule_polling(self):
        """Reschedule polling with current interval."""
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = Clock.schedule_interval(
                lambda _dt: self._poll_voice(),
                self._poll_current_interval
            )

    def _poll_voice(self):
        """Initiate voice chunk polling request."""
        with self._poll_lock:
            # Prevent overlapping requests
            if self._poll_in_flight:
                # Detect stale requests (timeout after 9 seconds)
                if self._poll_started_at > 0 and (time.time() - self._poll_started_at) > 9.0:
                    logger.warning("Voice poll request timeout (9s), marking as complete")
                    self._poll_in_flight = False
                    self._poll_started_at = 0.0
                else:
                    return

            # Validate room and player
            if not self._room_code or not self._player_name:
                return

            # Start new request
            self._poll_in_flight = True
            self._poll_started_at = time.time()
            self._poll_token += 1
            request_token = self._poll_token
            since_id = self._last_voice_id
            room_code = self._room_code
            player_name = self._player_name
            client_id = self._client_id

        logger.debug(
            f"Starting voice poll for room {room_code}, player {player_name} "
            f"(token={request_token}, since_id={since_id})"
        )

        # Execute in background thread
        Thread(
            target=self._poll_voice_worker,
            args=(request_token, room_code, player_name, client_id, since_id),
            daemon=True,
        ).start()

    def _poll_voice_worker(
        self,
        request_token: int,
        room_code: str,
        player_name: str,
        client_id: str,
        since_id: int,
    ):
        """Background worker for voice chunk polling.

        Args:
            request_token: Unique token for this request
            room_code: Room code
            player_name: Player name
            client_id: Client ID
            since_id: Last voice chunk ID seen
        """
        result = {
            "token": request_token,
            "status": "error",
            "message": "Failed to fetch voice chunks",
        }

        try:
            logger.debug(f"Voice poll worker: fetching chunks since {since_id}")
            response = get_room_voice_chunks(
                room_code=room_code,
                player_name=player_name,
                since_id=since_id if since_id > 0 else 0,
                client_id=client_id,
                timeout=4,
            )

            chunks = response.get("chunks", [])
            last_id = int(response.get("last_id") or since_id)

            logger.debug(
                f"Voice poll worker: received {len(chunks)} chunks, "
                f"last_id {since_id} -> {last_id}"
            )

            result = {
                "token": request_token,
                "status": "success",
                "chunks": chunks,
                "last_id": last_id,
            }

        except ConnectionError as error:
            logger.warning(f"Voice poll connection error: {error}")
            result["status"] = "connection_error"
            result["message"] = str(error)

        except ValueError as error:
            logger.warning(f"Voice poll validation error: {error}")
            result["status"] = "value_error"
            result["message"] = str(error)

        except Exception as error:
            logger.error(f"Voice poll unexpected error: {error}", exc_info=True)
            result["status"] = "error"
            result["message"] = str(error)

        Clock.schedule_once(lambda _dt, data=result: self._finish_poll_voice(data), 0)

    def _finish_poll_voice(self, payload: dict):
        """Handle voice polling response.

        Args:
            payload: Response data from worker
        """
        token = int(payload.get("token") or 0)

        with self._poll_lock:
            if token != self._poll_token:
                logger.debug(
                    f"Voice poll token mismatch: {token} vs {self._poll_token}, ignoring"
                )
                return
            self._poll_in_flight = False
            self._poll_started_at = 0.0

        status = payload.get("status")

        if status == "success":
            chunks = payload.get("chunks", [])
            last_id = int(payload.get("last_id") or 0)

            logger.debug(f"Voice poll success: {len(chunks)} chunks, updating last_id to {last_id}")

            # Update last voice ID
            self._last_voice_id = max(self._last_voice_id, last_id)

            # Send chunks to voice engine for playback
            if chunks and self.voice_engine is not None:
                self.voice_engine.queue_remote_chunks(chunks)

            # Success - reset error backoff
            self._reset_poll_backoff()

        elif status == "connection_error":
            logger.error(f"Voice poll connection error: {payload.get('message')}")
            self._apply_poll_backoff()

        elif status == "value_error":
            logger.warning(f"Voice poll validation error: {payload.get('message')}")
            self._apply_poll_backoff()

        else:
            logger.error(f"Voice poll error: {payload.get('message')}")
            self._apply_poll_backoff()

    def reset_for_new_room(self):
        """Reset controller state when entering new room."""
        self.stop_polling()
        with self._poll_lock:
            self._poll_in_flight = False
            self._poll_token = 0
            self._poll_started_at = 0.0
            self._last_voice_id = 0
            self._room_code = ""
            self._player_name = ""
            self._client_id = ""
