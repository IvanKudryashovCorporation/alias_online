"""Voice chunks polling with comprehensive diagnostics and crash protection."""

import config
import logging
import time
import traceback
from threading import Thread, Lock
from kivy.clock import Clock
from services import get_room_voice_chunks

logger = logging.getLogger(__name__)


class VoicePollingController:
    """Manages voice chunk fetching with diagnostic logging and safe error handling."""

    def __init__(self, voice_engine):
        """Initialize controller."""
        logger.info("[VoicePollingController] __init__ called")
        try:
            self.voice_engine = voice_engine
            self._poll_event = None
            self._poll_lock = Lock()
            self._poll_in_flight = False
            self._poll_token = 0
            self._poll_started_at = 0.0
            self._poll_current_interval = config.VOICE_POLLING_INTERVAL_SECONDS
            self._poll_consecutive_errors = 0
            self._last_voice_id = 0
            self._room_code = ""
            self._player_name = ""
            self._client_id = ""
            self._is_polling_active = False
            logger.info("[VoicePollingController] __init__ completed successfully")
        except Exception as e:
            logger.error(f"[VoicePollingController] __init__ CRASHED: {e}", exc_info=True)
            raise

    def start_polling(self, room_code: str, player_name: str, client_id: str = ""):
        """Start periodic voice chunk polling."""
        logger.info(
            f"[VoicePollingController.start_polling] ENTRY: "
            f"room_code={room_code}, player_name={player_name}, client_id={client_id}"
        )

        try:
            # Safety: already polling?
            if self._is_polling_active:
                logger.warning("[VoicePollingController.start_polling] Already active, stopping first")
                self.stop_polling()

            logger.debug("[VoicePollingController.start_polling] Stopping any existing poll event")
            if self._poll_event is not None:
                self._poll_event.cancel()
                self._poll_event = None

            # Validate inputs
            self._room_code = (room_code or "").strip().upper()
            self._player_name = (player_name or "").strip()
            self._client_id = (client_id or "").strip()

            if not self._room_code or not self._player_name:
                logger.warning(
                    f"[VoicePollingController.start_polling] Invalid inputs: "
                    f"room_code={self._room_code}, player_name={self._player_name}"
                )
                return

            logger.debug("[VoicePollingController.start_polling] Resetting state")
            self._last_voice_id = 0
            self._poll_current_interval = config.VOICE_POLLING_INTERVAL_SECONDS
            self._poll_consecutive_errors = 0
            self._poll_token = 0
            self._is_polling_active = True

            # Check if voice audio is disabled for debugging
            if config.DISABLE_VOICE_AUDIO_INIT:
                logger.warning(
                    "[VoicePollingController.start_polling] VOICE AUDIO DISABLED (debug mode). "
                    "Polling will not start."
                )
                self._is_polling_active = False
                return

            logger.debug(
                f"[VoicePollingController.start_polling] Scheduling interval: {self._poll_current_interval}s"
            )

            # THIS IS THE CRITICAL CALL - schedule_interval
            try:
                self._poll_event = Clock.schedule_interval(
                    self._poll_voice,
                    self._poll_current_interval
                )
                logger.info(
                    f"[VoicePollingController.start_polling] Clock.schedule_interval SUCCESS"
                )
            except Exception as e:
                logger.error(
                    f"[VoicePollingController.start_polling] Clock.schedule_interval FAILED: {e}",
                    exc_info=True
                )
                self._is_polling_active = False
                raise

            logger.info(
                f"[VoicePollingController.start_polling] SUCCESS. "
                f"Room={self._room_code}, Player={self._player_name}"
            )

        except Exception as e:
            logger.error(f"[VoicePollingController.start_polling] CRASHED: {e}", exc_info=True)
            self._is_polling_active = False
            raise

    def stop_polling(self):
        """Stop voice chunk polling."""
        logger.info("[VoicePollingController.stop_polling] ENTRY")
        try:
            if self._poll_event is not None:
                logger.debug("[VoicePollingController.stop_polling] Cancelling poll event")
                try:
                    self._poll_event.cancel()
                except Exception as e:
                    logger.warning(f"[VoicePollingController.stop_polling] Error cancelling event: {e}")
                self._poll_event = None

            self._is_polling_active = False
            logger.info("[VoicePollingController.stop_polling] SUCCESS")
        except Exception as e:
            logger.error(f"[VoicePollingController.stop_polling] CRASHED: {e}", exc_info=True)

    def _apply_poll_backoff(self):
        """Increase polling interval after error."""
        try:
            self._poll_consecutive_errors += 1
            new_interval = config.VOICE_POLLING_INTERVAL_SECONDS * (
                config.VOICE_POLLING_ERROR_BACKOFF_FACTOR ** self._poll_consecutive_errors
            )
            self._poll_current_interval = min(new_interval, config.VOICE_POLLING_MAX_BACKOFF_SECONDS)
            logger.warning(
                f"[VoicePollingController._apply_poll_backoff] "
                f"Error #{self._poll_consecutive_errors}, backoff to {self._poll_current_interval:.2f}s"
            )
            self._reschedule_polling()
        except Exception as e:
            logger.error(f"[VoicePollingController._apply_poll_backoff] CRASHED: {e}", exc_info=True)

    def _reset_poll_backoff(self):
        """Reset polling interval after success."""
        try:
            if self._poll_consecutive_errors > 0:
                logger.info(
                    f"[VoicePollingController._reset_poll_backoff] "
                    f"Resetting {self._poll_consecutive_errors} errors"
                )
                self._poll_consecutive_errors = 0
                self._poll_current_interval = config.VOICE_POLLING_INTERVAL_SECONDS
                self._reschedule_polling()
        except Exception as e:
            logger.error(f"[VoicePollingController._reset_poll_backoff] CRASHED: {e}", exc_info=True)

    def _reschedule_polling(self):
        """Reschedule polling with current interval."""
        try:
            if self._poll_event is not None:
                logger.debug(f"[VoicePollingController._reschedule_polling] Interval={self._poll_current_interval:.2f}s")
                self._poll_event.cancel()
                self._poll_event = Clock.schedule_interval(
                    self._poll_voice,
                    self._poll_current_interval
                )
        except Exception as e:
            logger.error(f"[VoicePollingController._reschedule_polling] CRASHED: {e}", exc_info=True)

    def _poll_voice(self, dt=None):
        """Clock callback for voice polling - MUST NOT CRASH."""
        try:
            if not config.VOICE_POLLING_DEBUG:
                return self._poll_voice_impl(dt)

            logger.debug(f"[VoicePollingController._poll_voice] Callback invoked (dt={dt})")
            return self._poll_voice_impl(dt)
        except Exception as e:
            # CRITICAL: Clock callback errors must be caught and logged
            logger.error(
                f"[VoicePollingController._poll_voice] Clock callback CRASHED: {e}",
                exc_info=True
            )
            # Return False to stop polling on crash
            return False

    def _poll_voice_impl(self, dt):
        """Implementation of poll voice - can raise exceptions."""
        # SAFETY: Don't poll if not fully ready
        if not self._is_polling_active:
            logger.debug(
                f"[VoicePollingController._poll_voice_impl] "
                f"Polling not active yet, skipping"
            )
            return True

        with self._poll_lock:
            # Check if already in flight
            if self._poll_in_flight:
                if self._poll_started_at > 0 and (
                    time.time() - self._poll_started_at
                ) > config.VOICE_POLLING_INFLIGHT_TIMEOUT_SECONDS:
                    logger.warning(
                        f"[VoicePollingController._poll_voice_impl] "
                        f"Request timeout ({config.VOICE_POLLING_INFLIGHT_TIMEOUT_SECONDS:.1f}s), marking as complete"
                    )
                    self._poll_in_flight = False
                    self._poll_started_at = 0.0
                else:
                    logger.debug(
                        f"[VoicePollingController._poll_voice_impl] "
                        f"Request already in flight, skipping"
                    )
                    return True

            # Validate room and player
            if not self._room_code or not self._player_name:
                logger.debug(
                    f"[VoicePollingController._poll_voice_impl] "
                    f"No room/player, skipping"
                )
                return True

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
            f"[VoicePollingController._poll_voice_impl] "
            f"Starting request (token={request_token}, since_id={since_id})"
        )

        # Execute in background thread
        try:
            logger.debug(
                f"[VoicePollingController._poll_voice_impl] "
                f"Spawning worker thread"
            )
            thread = Thread(
                target=self._poll_voice_worker,
                args=(request_token, room_code, player_name, client_id, since_id),
                daemon=True,
                name=f"VoicePollingWorker-{request_token}",
            )
            thread.start()
            logger.debug(
                f"[VoicePollingController._poll_voice_impl] "
                f"Worker thread started successfully"
            )
        except Exception as e:
            logger.error(
                f"[VoicePollingController._poll_voice_impl] "
                f"Failed to spawn worker thread: {e}",
                exc_info=True
            )
            with self._poll_lock:
                self._poll_in_flight = False
                self._poll_started_at = 0.0
            self._apply_poll_backoff()

        return True  # Keep polling

    def _poll_voice_worker(
        self,
        request_token: int,
        room_code: str,
        player_name: str,
        client_id: str,
        since_id: int,
    ):
        """Background worker for voice polling - MUST handle all exceptions."""
        logger.debug(
            f"[VoicePollingController._poll_voice_worker] "
            f"Worker started (token={request_token})"
        )

        result = {
            "token": request_token,
            "status": "error",
            "message": "Unexpected error in worker",
        }

        try:
            logger.debug(
                f"[VoicePollingController._poll_voice_worker] "
                f"Calling get_room_voice_chunks(room_code={room_code}, since_id={since_id})"
            )

            response = get_room_voice_chunks(
                room_code=room_code,
                player_name=player_name,
                since_id=since_id if since_id > 0 else 0,
                client_id=client_id,
                timeout=config.VOICE_POLLING_REQUEST_TIMEOUT_SECONDS,
            )

            chunks = response.get("chunks", [])
            last_id = int(response.get("last_id") or since_id)

            logger.debug(
                f"[VoicePollingController._poll_voice_worker] "
                f"Success: {len(chunks)} chunks, last_id={last_id}"
            )

            result = {
                "token": request_token,
                "status": "success",
                "chunks": chunks,
                "last_id": last_id,
            }

        except ConnectionError as error:
            logger.warning(
                f"[VoicePollingController._poll_voice_worker] "
                f"ConnectionError: {error}"
            )
            result["status"] = "connection_error"
            result["message"] = str(error)

        except ValueError as error:
            logger.warning(
                f"[VoicePollingController._poll_voice_worker] "
                f"ValueError: {error}"
            )
            result["status"] = "value_error"
            result["message"] = str(error)

        except Exception as error:
            logger.error(
                f"[VoicePollingController._poll_voice_worker] "
                f"UNEXPECTED ERROR: {error}",
                exc_info=True
            )
            result["status"] = "error"
            result["message"] = str(error)

        logger.debug(
            f"[VoicePollingController._poll_voice_worker] "
            f"Scheduling callback (token={request_token}, status={result['status']})"
        )

        try:
            Clock.schedule_once(
                lambda _dt, data=result: self._finish_poll_voice(data),
                0
            )
        except Exception as e:
            logger.error(
                f"[VoicePollingController._poll_voice_worker] "
                f"Failed to schedule callback: {e}",
                exc_info=True
            )

    def _finish_poll_voice(self, payload: dict):
        """Handle voice polling response in UI thread."""
        logger.debug(
            f"[VoicePollingController._finish_poll_voice] "
            f"ENTRY (token={payload.get('token')}, status={payload.get('status')})"
        )

        try:
            token = int(payload.get("token") or 0)

            with self._poll_lock:
                if token != self._poll_token:
                    logger.debug(
                        f"[VoicePollingController._finish_poll_voice] "
                        f"Token mismatch: {token} vs {self._poll_token}, ignoring stale"
                    )
                    return
                self._poll_in_flight = False
                self._poll_started_at = 0.0

            status = payload.get("status")

            if status == "success":
                chunks = payload.get("chunks", [])
                last_id = int(payload.get("last_id") or 0)

                logger.debug(
                    f"[VoicePollingController._finish_poll_voice] "
                    f"Success: {len(chunks)} chunks, queuing for playback"
                )

                # Update last voice ID
                self._last_voice_id = max(self._last_voice_id, last_id)

                # Queue chunks for playback
                if chunks and self.voice_engine is not None:
                    try:
                        self.voice_engine.queue_remote_chunks(chunks)
                    except Exception as e:
                        logger.error(
                            f"[VoicePollingController._finish_poll_voice] "
                            f"Error queueing chunks: {e}",
                            exc_info=True
                        )

                # Reset backoff
                self._reset_poll_backoff()

            else:
                message = payload.get("message") or "Unknown error"
                logger.error(
                    f"[VoicePollingController._finish_poll_voice] "
                    f"Error: {status}: {message}"
                )
                self._apply_poll_backoff()

        except Exception as e:
            logger.error(
                f"[VoicePollingController._finish_poll_voice] "
                f"CRASHED: {e}",
                exc_info=True
            )

    def reset_for_new_room(self):
        """Reset controller state when entering new room."""
        logger.info("[VoicePollingController.reset_for_new_room] ENTRY")
        try:
            self.stop_polling()
            with self._poll_lock:
                self._poll_in_flight = False
                self._poll_token = 0
                self._poll_started_at = 0.0
                self._last_voice_id = 0
                self._room_code = ""
                self._player_name = ""
                self._client_id = ""
                self._is_polling_active = False
            logger.info("[VoicePollingController.reset_for_new_room] SUCCESS")
        except Exception as e:
            logger.error(
                f"[VoicePollingController.reset_for_new_room] CRASHED: {e}",
                exc_info=True
            )
