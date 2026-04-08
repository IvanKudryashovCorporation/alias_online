import base64
import logging
import math
import queue
import sys
import threading
import time
from array import array

import config
from kivy.utils import platform

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError as e:
    logger.warning(f"numpy not available (desktop voice backend disabled): {e}")
    np = None

try:
    import sounddevice as sd
except ImportError as e:
    logger.warning(f"sounddevice not available (desktop voice backend disabled): {e}")
    sd = None

_ANDROID_AUDIO_AVAILABLE = False
AudioRecord = None
AudioTrack = None
AudioFormat = None
AudioManager = None
AudioSource = None

if platform == "android":
    try:
        from jnius import autoclass

        AudioRecord = autoclass("android.media.AudioRecord")
        AudioTrack = autoclass("android.media.AudioTrack")
        AudioFormat = autoclass("android.media.AudioFormat")
        AudioManager = autoclass("android.media.AudioManager")
        AudioSource = autoclass("android.media.MediaRecorder$AudioSource")
        _ANDROID_AUDIO_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Android audio classes are unavailable: {e}")

from .room_hub import send_room_voice_chunk


class RoomVoiceEngine:
    def __init__(
        self,
        sample_rate=config.VOICE_SAMPLE_RATE,
        block_frames=config.VOICE_BLOCK_FRAMES,
    ):
        self.sample_rate = int(sample_rate)
        self.block_frames = int(block_frames)
        self._block_bytes = max(2, self.block_frames * 2)

        self._backend = self._select_backend()
        self.available = self._backend is not None

        self.room_code = ""
        self.player_name = ""
        self._should_transmit = lambda: False
        self._active = False
        self._muted = True
        self._level = 0.0

        self._input_stream = None
        self._output_stream = None

        self._android_input = None
        self._android_output = None
        self._android_capture_thread = None
        self._android_play_thread = None
        self._android_record_buffer_bytes = self._block_bytes
        self._android_read_bytes = self._block_bytes

        self._stop_event = threading.Event()
        self._send_queue = queue.Queue(maxsize=max(8, int(config.VOICE_SEND_QUEUE_MAX_FRAMES)))
        self._play_queue = queue.Queue(maxsize=max(6, int(config.VOICE_PLAY_QUEUE_MAX_FRAMES)))

        # Desktop playback buffer (numpy float32)
        self._play_buffer = None
        # Android playback buffer (pcm16 bytes)
        self._android_pending_bytes = bytearray()

        self._send_thread = None
        self._lock = threading.Lock()

    def _select_backend(self):
        if platform == "android":
            return "android" if _ANDROID_AUDIO_AVAILABLE else None
        if sd is not None and np is not None:
            return "sounddevice"
        return None

    def start(self, *, room_code, player_name, should_transmit):
        with self._lock:
            if not self.available or self._active:
                return
            self._active = True

        self.room_code = (room_code or "").strip().upper()
        self.player_name = (player_name or "").strip()
        self._should_transmit = should_transmit or (lambda: False)
        self._stop_event.clear()
        self._android_pending_bytes = bytearray()

        try:
            if self._backend == "android":
                self._start_android_streams()
            elif self._backend == "sounddevice":
                self._start_sounddevice_streams()
            else:
                raise RuntimeError("No supported voice backend selected")
        except Exception as e:
            logger.error(f"Failed to initialize audio streams: {e}", exc_info=True)
            self.stop()
            if self._backend != "android":
                self.available = False
            return

        self._send_thread = threading.Thread(target=self._send_loop, daemon=True, name="VoiceSendLoop")
        self._send_thread.start()

    def _start_sounddevice_streams(self):
        self._input_stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block_frames,
            latency="low",
            callback=self._input_callback,
        )
        self._input_stream.start()

        self._output_stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block_frames,
            latency="low",
            callback=self._output_callback,
        )
        self._output_stream.start()

    def _start_android_streams(self):
        if not _ANDROID_AUDIO_AVAILABLE:
            raise RuntimeError("Android audio classes are unavailable")

        channel_in = int(AudioFormat.CHANNEL_IN_MONO)
        channel_out = int(AudioFormat.CHANNEL_OUT_MONO)
        encoding = int(AudioFormat.ENCODING_PCM_16BIT)

        min_in = int(AudioRecord.getMinBufferSize(self.sample_rate, channel_in, encoding))
        min_out = int(AudioTrack.getMinBufferSize(self.sample_rate, channel_out, encoding))
        if min_in <= 0 or min_out <= 0:
            raise RuntimeError(f"Invalid Android audio buffer sizes: in={min_in}, out={min_out}")

        # Keep the recorder buffer stable, but read short frames for low latency.
        self._android_record_buffer_bytes = max(self._block_bytes * 2, min_in)
        self._android_read_bytes = self._block_bytes
        play_bytes = max(self._block_bytes * 2, min_out)

        self._android_input = AudioRecord(
            int(AudioSource.MIC),
            self.sample_rate,
            channel_in,
            encoding,
            self._android_record_buffer_bytes,
        )
        if int(self._android_input.getState()) != int(AudioRecord.STATE_INITIALIZED):
            raise RuntimeError("AudioRecord failed to initialize")

        self._android_output = AudioTrack(
            int(AudioManager.STREAM_MUSIC),
            self.sample_rate,
            channel_out,
            encoding,
            play_bytes,
            int(AudioTrack.MODE_STREAM),
        )
        if int(self._android_output.getState()) != int(AudioTrack.STATE_INITIALIZED):
            raise RuntimeError("AudioTrack failed to initialize")

        self._android_input.startRecording()
        self._android_output.play()

        self._android_capture_thread = threading.Thread(
            target=self._android_capture_loop,
            daemon=True,
            name="VoiceAndroidCapture",
        )
        self._android_capture_thread.start()

        self._android_play_thread = threading.Thread(
            target=self._android_play_loop,
            daemon=True,
            name="VoiceAndroidPlay",
        )
        self._android_play_thread.start()

    def stop(self):
        self._stop_event.set()
        with self._lock:
            self._active = False

        if self._backend == "android":
            self._stop_android_streams()
        elif self._backend == "sounddevice":
            self._stop_sounddevice_streams()

        self._join_thread(self._android_capture_thread)
        self._join_thread(self._android_play_thread)
        self._join_thread(self._send_thread)

        self._android_capture_thread = None
        self._android_play_thread = None
        self._send_thread = None
        self._play_buffer = None
        self._android_pending_bytes = bytearray()

        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                break

        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except queue.Empty:
                break

        with self._lock:
            self._level = 0.0

    def _stop_sounddevice_streams(self):
        if self._input_stream is not None:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception as e:
                logger.debug(f"Error stopping input stream: {e}")
            self._input_stream = None

        if self._output_stream is not None:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception as e:
                logger.debug(f"Error stopping output stream: {e}")
            self._output_stream = None

    def _stop_android_streams(self):
        if self._android_input is not None:
            try:
                self._android_input.stop()
            except Exception as e:
                logger.debug(f"Error stopping AudioRecord: {e}")
            try:
                self._android_input.release()
            except Exception as e:
                logger.debug(f"Error releasing AudioRecord: {e}")
            self._android_input = None

        if self._android_output is not None:
            try:
                self._android_output.pause()
            except Exception:
                pass
            try:
                self._android_output.flush()
            except Exception:
                pass
            try:
                self._android_output.stop()
            except Exception as e:
                logger.debug(f"Error stopping AudioTrack: {e}")
            try:
                self._android_output.release()
            except Exception as e:
                logger.debug(f"Error releasing AudioTrack: {e}")
            self._android_output = None

    @staticmethod
    def _join_thread(thread_obj):
        if thread_obj is None:
            return
        try:
            if thread_obj.is_alive() and thread_obj is not threading.current_thread():
                thread_obj.join(timeout=0.45)
        except Exception:
            pass

    def set_muted(self, muted):
        with self._lock:
            self._muted = bool(muted)
            if self._muted:
                self._level = 0.0

    def is_muted(self):
        with self._lock:
            return self._muted

    def level(self):
        with self._lock:
            return float(self._level)

    def active(self):
        with self._lock:
            return self._active and self.available

    def _set_level(self, value):
        with self._lock:
            self._level = max(0.0, min(1.0, float(value)))

    @staticmethod
    def _rms_from_pcm16_bytes(raw_bytes):
        if not raw_bytes:
            return 0.0

        samples = array("h")
        try:
            samples.frombytes(raw_bytes)
        except Exception:
            return 0.0

        if not samples:
            return 0.0

        if sys.byteorder != "little":
            try:
                samples.byteswap()
            except Exception:
                return 0.0

        # Light decimation to keep CPU usage low on weaker devices.
        step = 2 if len(samples) > 640 else 1
        sum_sq = 0
        count = 0
        for idx in range(0, len(samples), step):
            val = int(samples[idx])
            sum_sq += val * val
            count += 1

        if count <= 0:
            return 0.0
        return math.sqrt(sum_sq / float(count)) / 32768.0

    def _input_callback(self, indata, frames, _time_info, status):
        if status:
            return
        if indata is None or frames <= 0:
            self._set_level(0.0)
            return
        if np is None:
            self._set_level(0.0)
            return

        try:
            mono = indata[:, 0]
        except Exception:
            self._set_level(0.0)
            return

        clean = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
        clean = np.clip(clean, -1.0, 1.0)
        rms = float(np.sqrt(np.mean(clean * clean))) if clean.size else 0.0
        level = min(1.0, max(0.0, (rms - 0.003) * 22.0))

        with self._lock:
            is_muted = self._muted
            self._level = max(0.0, min(1.0, float(0.0 if is_muted else level)))

        if is_muted or not self._should_transmit() or not self.room_code:
            return

        pcm16_bytes = (clean * 32767.0).astype(np.int16).tobytes()
        self._enqueue_send_pcm16(pcm16_bytes)

    def _enqueue_send_pcm16(self, pcm16_bytes):
        payload = {
            "room_code": self.room_code,
            "player_name": self.player_name,
            "pcm16_bytes": bytes(pcm16_bytes),
            "sample_rate": self.sample_rate,
        }
        try:
            self._send_queue.put_nowait(payload)
        except queue.Full:
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._send_queue.put_nowait(payload)
            except queue.Full:
                logger.debug("Voice send queue still full, dropping newest frame")

    def _output_callback(self, outdata, frames, _time_info, status):
        if status:
            outdata.fill(0)
            return
        if np is None:
            outdata.fill(0)
            return

        outdata.fill(0)
        written = 0
        while written < frames:
            if self._play_buffer is None or len(self._play_buffer) == 0:
                try:
                    self._play_buffer = self._play_queue.get_nowait()
                except queue.Empty:
                    break

            take = min(frames - written, len(self._play_buffer))
            outdata[written : written + take, 0] = self._play_buffer[:take]
            self._play_buffer = self._play_buffer[take:]
            written += take

    def _android_capture_loop(self):
        while not self._stop_event.is_set():
            recorder = self._android_input
            if recorder is None:
                break

            raw_buf = bytearray(self._android_read_bytes)
            try:
                read_bytes = int(recorder.read(raw_buf, 0, self._android_read_bytes))
            except Exception as e:
                logger.debug(f"Android AudioRecord read failed: {e}")
                time.sleep(0.03)
                continue

            if read_bytes <= 0:
                time.sleep(0.005)
                continue

            if read_bytes % 2 == 1:
                read_bytes -= 1
            if read_bytes <= 0:
                continue

            pcm16_bytes = bytes(raw_buf[:read_bytes])
            rms = self._rms_from_pcm16_bytes(pcm16_bytes)
            level = min(1.0, max(0.0, (rms - 0.003) * 22.0))

            with self._lock:
                is_muted = self._muted
                self._level = max(0.0, min(1.0, float(0.0 if is_muted else level)))

            if is_muted or not self._should_transmit() or not self.room_code:
                continue

            self._enqueue_send_pcm16(pcm16_bytes)

    def _android_play_loop(self):
        pending = self._android_pending_bytes
        block_bytes = self._block_bytes
        # Keep no more than ~80 ms of pending audio.
        max_pending = block_bytes * 4

        while not self._stop_event.is_set():
            output = self._android_output
            if output is None:
                break

            if len(pending) < block_bytes:
                try:
                    chunk = self._play_queue.get(timeout=0.05)
                    if isinstance(chunk, (bytes, bytearray)) and len(chunk) > 0:
                        pending.extend(chunk)
                except queue.Empty:
                    pass

            if len(pending) > max_pending:
                del pending[:-max_pending]

            if len(pending) == 0:
                continue

            frame = bytearray(pending[:block_bytes])
            del pending[:block_bytes]
            if len(frame) < block_bytes:
                frame.extend(b"\x00" * (block_bytes - len(frame)))

            try:
                output.write(frame, 0, len(frame))
            except Exception as e:
                logger.debug(f"Android AudioTrack write failed: {e}")
                time.sleep(0.01)

    def _send_loop(self):
        while not self._stop_event.is_set():
            try:
                payload = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                chunks = []
                first_chunk = payload.get("pcm16_bytes") or b""
                if first_chunk:
                    chunks.append(bytes(first_chunk))

                batch_target = max(1, int(config.VOICE_SEND_BATCH_FRAMES))
                for _ in range(batch_target - 1):
                    try:
                        next_payload = self._send_queue.get_nowait()
                    except queue.Empty:
                        break
                    next_chunk = next_payload.get("pcm16_bytes") or b""
                    if next_chunk:
                        chunks.append(bytes(next_chunk))

                if not chunks:
                    continue

                merged_pcm16 = b"".join(chunks)
                send_room_voice_chunk(
                    room_code=payload["room_code"],
                    player_name=payload["player_name"],
                    pcm16_b64=base64.b64encode(merged_pcm16).decode("ascii"),
                    sample_rate=payload["sample_rate"],
                )
            except Exception as e:
                logger.warning(f"Failed to send voice chunk: {e}")
                time.sleep(0.15)

    def _resample_pcm_float(self, pcm, src_rate, dst_rate):
        if np is None:
            return pcm

        src = int(src_rate or 0)
        dst = int(dst_rate or 0)
        if pcm.size == 0 or src <= 0 or dst <= 0 or src == dst:
            return pcm.astype(np.float32, copy=False)

        src_len = int(pcm.size)
        dst_len = max(1, int(src_len * float(dst) / float(src)))
        if dst_len == src_len:
            return pcm.astype(np.float32, copy=False)

        src_axis = np.linspace(0.0, 1.0, num=src_len, endpoint=False, dtype=np.float32)
        dst_axis = np.linspace(0.0, 1.0, num=dst_len, endpoint=False, dtype=np.float32)
        resampled = np.interp(dst_axis, src_axis, pcm).astype(np.float32)
        return np.clip(resampled, -1.0, 1.0)

    def _enqueue_play_payload(self, payload):
        try:
            self._play_queue.put_nowait(payload)
            return
        except queue.Full:
            pass

        # Drop old queued audio to keep latency low.
        for _ in range(2):
            try:
                self._play_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._play_queue.put_nowait(payload)
        except queue.Full:
            logger.debug("Voice play queue still full, dropping frame")

    def queue_remote_chunks(self, chunks: list):
        """Queue remote voice chunks for playback."""
        if not chunks:
            return

        # If polling returns a burst, keep only newest chunks to avoid delayed speech playback.
        max_burst = max(4, self._play_queue.maxsize // 2)
        if len(chunks) > max_burst:
            chunks = chunks[-max_burst:]

        for chunk in chunks:
            encoded = (chunk or {}).get("pcm16_b64") or ""
            if not encoded:
                continue

            try:
                raw = base64.b64decode(encoded)
            except Exception:
                continue

            if not raw:
                continue

            try:
                source_rate = int((chunk or {}).get("sample_rate") or self.sample_rate)
            except (TypeError, ValueError):
                source_rate = self.sample_rate

            if self._backend == "android":
                if source_rate != self.sample_rate and np is not None:
                    # Rare compatibility case with mixed client versions.
                    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
                    pcm = self._resample_pcm_float(pcm, source_rate, self.sample_rate)
                    raw = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                self._enqueue_play_payload(raw)
                continue

            if np is None:
                continue

            try:
                pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
            except Exception:
                continue

            if pcm.size == 0:
                continue

            pcm = self._resample_pcm_float(pcm, source_rate, self.sample_rate)
            self._enqueue_play_payload(pcm.astype(np.float32, copy=False))
