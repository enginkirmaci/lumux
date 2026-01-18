"""Batched, coalescing light update worker to offload Hue bridge calls."""

import threading
import time
from typing import Dict, Any, Optional


class LightUpdateWorker:
    def __init__(self, bridge, flush_interval_ms: int = 100):
        self.bridge = bridge
        self.flush_interval = max(10, int(flush_interval_ms)) / 1000.0
        self._latest_updates: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stats = {'last_flush_count': 0, 'flushs': 0}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="LightUpdater", daemon=True)
        self._thread.start()
        print(f"LightUpdateWorker started (flush_interval={self.flush_interval}s)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def enqueue(self, light_id: str, payload: Dict[str, Any]):
        """Store the latest payload for a light (coalesce)."""
        with self._lock:
            self._latest_updates[light_id] = payload

    def get_stats(self):
        with self._lock:
            return dict(self._stats)

    def _run(self):
        while not self._stop_event.is_set():
            start = time.time()
            self._flush()
            elapsed = time.time() - start
            to_sleep = self.flush_interval - elapsed
            if to_sleep > 0:
                self._stop_event.wait(to_sleep)

    def _flush(self):
        with self._lock:
            updates = self._latest_updates
            self._latest_updates = {}

        if not updates:
            return

        sent = 0
        for light_id, payload in updates.items():
            try:
                ptype = payload.get('type')
                if ptype == 'gradient':
                    # Expect payload to contain fixed_points and brightness
                    fixed_points = payload.get('fixed_points', [])
                    brightness = int(payload.get('brightness', 0))
                    self.bridge.set_light_gradient(light_id, fixed_points, brightness)
                elif ptype == 'color':
                    xy = payload.get('xy')
                    br = payload.get('brightness')
                    trans = payload.get('transition_time', None)
                    self.bridge.set_light_color(light_id, xy, br, transition_time=trans)
                else:
                    # Unknown payload: skip
                    continue
                sent += 1
            except Exception as e:
                print(f"LightUpdateWorker: error sending update for {light_id}: {e}")

        with self._lock:
            self._stats['last_flush_count'] = sent
            self._stats['flushs'] = self._stats.get('flushs', 0) + 1
