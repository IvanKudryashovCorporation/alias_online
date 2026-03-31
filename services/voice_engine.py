import base64
import queue
import threading
import time

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

from .room_hub import get_room_voice_chunks, send_room_voice_chunk


class RoomVoiceEngine:
    def __init__(self, sample_rate=24000, block_frames=960):
        self.sample_rate = int(sample_rate)
        self.block_frames = int(block_frames)

        self.available = np is not None and sd is not None
        self.room_code = ""
        self.player_name = ""
        self._should_transmit = lambda: False
        self._active = False
        self._muted = True
        self._level = 0.0

        self._input_stream = None
        self._output_stream = None
        self._stop_event = threading.Event()
        self._send_queue = queue.Queue(maxsize=24)
        self._play_queue = queue.Queue(maxsize=64)
        self._play_buffer = None
        self._last_voice_id = 0

        self._send_thread = None
        self._recv_thread = None
        self._lock = threading.Lock()
        self._agc_gain = 1.0

    def start(self, *, room_code, player_name, should_transmit):
        if not self.available or self._active:
            return

        self.room_code = (room_code or "").strip().upper()
        self.player_name = (player_name or "").strip()
        self._should_transmit = should_transmit or (lambda: False)
        self._stop_event.clear()
        self._last_voice_id = 0
        self._active = True

        try:
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
        except Exception:
            self.stop()
            self.available = False
            return

        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._send_thread.start()
        self._recv_thread.start()

    def stop(self):
        self._stop_event.set()
        self._active = False

        if self._input_stream is not None:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception:
                pass
            self._input_stream = None

        if self._output_stream is not None:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None

        self._send_thread = None
        self._recv_thread = None
        self._play_buffer = None

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
        self._agc_gain = 1.0

    def set_muted(self, muted):
        self._muted = bool(muted)
        if self._muted:
            with self._lock:
                self._level = 0.0

    def is_muted(self):
        return self._muted

    def level(self):
        with self._lock:
            return float(self._level)

    def active(self):
        return self._active and self.available

    def _set_level(self, value):
        with self._lock:
            self._level = max(0.0, min(1.0, float(value)))

    def _prepare_capture_audio(self, mono):
        if mono.size == 0:
            return mono

        clean = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
        if clean.size > 1:
            # Gentle pre-emphasis keeps speech consonants clearer in compressed voice chunks.
            clean = np.concatenate(([clean[0]], clean[1:] - 0.95 * clean[:-1])).astype(np.float32, copy=False)

        rms = float(np.sqrt(np.mean(clean * clean))) if clean.size else 0.0
        if rms < 0.0038:
            return np.zeros_like(clean, dtype=np.float32)

        peak = float(np.max(np.abs(clean))) if clean.size else 0.0
        if peak > 0:
            target_peak = 0.82
            desired_gain = max(0.7, min(4.0, target_peak / peak))
            self._agc_gain += (desired_gain - self._agc_gain) * 0.24
            clean = clean * self._agc_gain

        clean = np.clip(clean, -1.0, 1.0).astype(np.float32, copy=False)
        return clean

    def _resample_pcm(self, pcm, src_rate, dst_rate):
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

    def _input_callback(self, indata, frames, _time_info, status):
        if status:
            return
        if indata is None or frames <= 0:
            self._set_level(0.0)
            return

        mono = self._prepare_capture_audio(indata[:, 0].copy())
        rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
        level = min(1.0, max(0.0, (rms - 0.004) * 12.5))
        self._set_level(0.0 if self._muted else level)

        if self._muted or not self._should_transmit() or not self.room_code:
            return

        pcm = np.clip(mono, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16).tobytes()
        encoded = base64.b64encode(pcm16).decode("ascii")
        payload = {
            "room_code": self.room_code,
            "player_name": self.player_name,
            "pcm16_b64": encoded,
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
                pass

    def _output_callback(self, outdata, frames, _time_info, status):
        if status:
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

    def _send_loop(self):
        while not self._stop_event.is_set():
            try:
                payload = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                send_room_voice_chunk(
                    room_code=payload["room_code"],
                    player_name=payload["player_name"],
                    pcm16_b64=payload["pcm16_b64"],
                    sample_rate=payload["sample_rate"],
                )
            except Exception:
                time.sleep(0.2)

    def _recv_loop(self):
        while not self._stop_event.is_set():
            if not self.room_code:
                time.sleep(0.2)
                continue

            try:
                response = get_room_voice_chunks(
                    room_code=self.room_code,
                    player_name=self.player_name,
                    since_id=self._last_voice_id,
                )
            except Exception:
                time.sleep(0.3)
                continue

            chunks = response.get("chunks", [])
            last_id = int(response.get("last_id") or self._last_voice_id)
            self._last_voice_id = max(self._last_voice_id, last_id)

            for chunk in chunks:
                encoded = chunk.get("pcm16_b64") or ""
                if not encoded:
                    continue

                try:
                    raw = base64.b64decode(encoded)
                    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
                except Exception:
                    continue

                if pcm.size == 0:
                    continue

                try:
                    source_rate = int(chunk.get("sample_rate") or self.sample_rate)
                except (TypeError, ValueError):
                    source_rate = self.sample_rate
                pcm = self._resample_pcm(pcm, source_rate, self.sample_rate)

                # Tiny fade-in/out avoids clicks between chunks.
                if pcm.size >= 8:
                    fade_len = min(24, pcm.size // 4)
                    if fade_len > 0:
                        fade = np.linspace(0.0, 1.0, num=fade_len, dtype=np.float32)
                        pcm[:fade_len] *= fade
                        pcm[-fade_len:] *= fade[::-1]
                pcm = np.tanh(pcm * 1.08).astype(np.float32, copy=False)

                try:
                    self._play_queue.put_nowait(pcm)
                except queue.Full:
                    try:
                        self._play_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._play_queue.put_nowait(pcm)
                    except queue.Full:
                        pass

            time.sleep(0.08)
