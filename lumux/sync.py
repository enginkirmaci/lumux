"""Main sync controller with threading."""

import queue
import threading
import time
from typing import Dict, Tuple, Optional
from datetime import datetime


def _timed_print(*args, **kwargs):
    prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(prefix, *args, **kwargs)

from lumux.bridge import HueBridge
from lumux.capture import ScreenCapture
from lumux.zones import ZoneProcessor
from lumux.colors import ColorAnalyzer
from lumux.entertainment import EntertainmentStream
from lumux.black_bar_detector import BlackBarDetector
from config.zone_mapping import ZoneMapping


class SyncController:
    def __init__(self, bridge: HueBridge, capture: ScreenCapture,
                 zone_processor: ZoneProcessor, color_analyzer: ColorAnalyzer,
                 zone_mapping: ZoneMapping, settings, 
                 entertainment_stream: Optional[EntertainmentStream] = None):
        self.bridge = bridge
        self.capture = capture
        self.zone_processor = zone_processor
        self.color_analyzer = color_analyzer
        self.zone_mapping = zone_mapping
        self.settings = settings
        self.entertainment_stream = entertainment_stream

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.previous_colors: Dict[str, Tuple[Tuple[float, float], int]] = {}
        self.queue: queue.Queue = queue.Queue(maxsize=100)
        self.lock = threading.Lock()

        # Zone to channel mapping for entertainment streaming
        self._zone_channel_map: Dict[str, int] = {}

        # Black bar detection
        self._black_bar_detector: Optional[BlackBarDetector] = None
        self._frame_counter = 0
        self._init_black_bar_detector()

        self._stats = {
            'fps': 0,
            'frame_count': 0,
            'errors': 0,
            'last_update': time.time()
        }

    def _init_black_bar_detector(self):
        """Initialize black bar detector if enabled in settings."""
        zone_settings = getattr(self.settings, 'zones', None)
        if zone_settings and getattr(zone_settings, 'ignore_black_bars', False):
            threshold = getattr(zone_settings, 'black_bar_threshold', 10)
            self._black_bar_detector = BlackBarDetector(threshold=threshold, min_size_percent=5.0)
            _timed_print(f"Black bar detection enabled (threshold={threshold})")
        else:
            self._black_bar_detector = None

    def start(self):
        """Start sync thread."""
        if self.running:
            return

        # Build zone to channel mapping for entertainment streaming
        if self.entertainment_stream:
            _timed_print(f"Entertainment stream object exists, connected={self.entertainment_stream.is_connected()}")
            if self.entertainment_stream.is_connected():
                self._build_zone_channel_mapping()
                _timed_print(f"Using entertainment streaming with {len(self._zone_channel_map)} zone-channel mappings")
            else:
                _timed_print("Warning: Entertainment stream exists but not connected")
        else:
            _timed_print("Warning: No entertainment stream configured")

        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True, name="SyncLoop")
        self.thread.start()

    def _build_zone_channel_mapping(self):
        """Build mapping from screen zones to entertainment channels based on positions."""
        if not self.entertainment_stream:
            return

        self._zone_channel_map.clear()
        channel_positions = self.entertainment_stream.get_channel_positions()

        if not channel_positions:
            _timed_print("Warning: No channel positions available")
            return

        # Get all zone IDs for ambilight layout
        # top_0..top_n, left_0..left_n, right_0..right_n, bottom_0..bottom_n
        zones = []
        for edge in ['top', 'bottom', 'left', 'right']:
            if edge in ['top', 'bottom']:
                count = self.zone_processor.cols
            else:
                count = max(1, self.zone_processor.rows // 2)
            for i in range(count):
                zones.append(f"{edge}_{i}")

        # Map each zone to nearest channel based on position
        for zone_id in zones:
            channel_id = self._find_best_channel_for_zone(zone_id, channel_positions)
            if channel_id is not None:
                self._zone_channel_map[zone_id] = channel_id

        _timed_print(f"Zone-channel mapping: {len(self._zone_channel_map)} zones mapped to {len(set(self._zone_channel_map.values()))} channels")

    def _find_best_channel_for_zone(self, zone_id: str, channel_positions: Dict[int, dict]) -> Optional[int]:
        """Find the best matching channel for a screen zone based on position."""
        try:
            parts = zone_id.split('_')
            if len(parts) == 2:
                edge, idx_str = parts
                idx = int(idx_str)
            else:
                # Grid zone like "0_0"
                return list(channel_positions.keys())[0] if channel_positions else None
        except ValueError:
            return list(channel_positions.keys())[0] if channel_positions else None

        # Convert screen edge/index to expected position range
        # Entertainment positions: x is left(-1) to right(+1), z is bottom(-1) to top(+1)
        if edge == 'left':
            target_x = -1.0
            # Left zones go from top (idx=0) to bottom (idx=n)
            target_z = 1.0 - (idx * 2.0 / max(1, self.zone_processor.rows // 2 - 1)) if self.zone_processor.rows > 2 else 0
        elif edge == 'right':
            target_x = 1.0
            target_z = 1.0 - (idx * 2.0 / max(1, self.zone_processor.rows // 2 - 1)) if self.zone_processor.rows > 2 else 0
        elif edge == 'top':
            target_z = 1.0
            target_x = -1.0 + (idx * 2.0 / max(1, self.zone_processor.cols - 1)) if self.zone_processor.cols > 1 else 0
        elif edge == 'bottom':
            target_z = -1.0
            target_x = -1.0 + (idx * 2.0 / max(1, self.zone_processor.cols - 1)) if self.zone_processor.cols > 1 else 0
        else:
            return list(channel_positions.keys())[0] if channel_positions else None

        # Find closest channel
        best_channel = None
        best_distance = float('inf')

        for channel_id, pos in channel_positions.items():
            cx = pos.get('x', 0)
            cz = pos.get('z', 0)
            distance = (cx - target_x) ** 2 + (cz - target_z) ** 2
            if distance < best_distance:
                best_distance = distance
                best_channel = channel_id

        return best_channel

    def stop(self):
        """Stop sync thread."""
        if not self.running:
            return

        self.running = False
        
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                _timed_print("Warning: Sync thread did not stop cleanly")
        
        # Stop the capture pipeline to release portal session
        if hasattr(self.capture, 'stop_pipeline'):
            self.capture.stop_pipeline()

    def is_running(self) -> bool:
        """Check if sync is running."""
        return self.running

    def _sync_loop(self):
        """Main sync loop (runs in background thread)."""
        frame_times = []
        
        while self.running:
            try:
                start_time = time.time()

                self._process_frame()

                # Time spent processing the frame (capture + analyze + update)
                elapsed = time.time() - start_time

                # Enforce and clamp configured FPS to safe range (1-60)
                try:
                    fps_target = int(getattr(self.settings, 'fps', 30))
                except Exception:
                    fps_target = 30

                fps_target = max(1, min(60, fps_target))
                target_delay = 1.0 / fps_target

                # Sleep the remaining time to meet target FPS
                delay = max(0, target_delay - elapsed)
                time.sleep(delay)

                # Measure full loop time including sleep to compute real FPS
                total_time = time.time() - start_time
                frame_times.append(total_time)

                if len(frame_times) > 30:
                    frame_times.pop(0)

                avg_frame_time = sum(frame_times) / len(frame_times)
                self._stats['fps'] = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
                self._stats['frame_count'] += 1

                # Debug: occasionally log the effective target and measured FPS
                if self._stats['frame_count'] % 100 == 0:
                    _timed_print(f"Sync target FPS={fps_target}, target_delay={target_delay:.4f}s, measured_fps={self._stats['fps']:.1f}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                self._stats['errors'] += 1
                _timed_print(f"Sync loop error: {e}")
                self._queue_status('error', str(e), None)
                time.sleep(1)

        self._queue_status('status', 'stopped', None)

    def _process_frame(self):
        """Process a single frame."""
        import time

        t0 = time.time()

        t_capture = time.time()
        screen = self.capture.capture()
        t_capture = time.time() - t_capture
        if not screen:
            return

        # Black bar detection (runs periodically)
        self._frame_counter += 1
        if self._black_bar_detector is not None:
            detection_rate = getattr(self.settings.zones, 'black_bar_detection_rate', 30)
            if self._frame_counter % detection_rate == 0:
                crop = self._black_bar_detector.detect(screen)
                self.zone_processor.update_black_bar_crop(crop, smoothing_factor=self.settings.smoothing_factor)

        t_zones = time.time()
        zone_colors = self.zone_processor.process_image(screen)
        t_zones = time.time() - t_zones
        if not zone_colors or len(zone_colors) == 0:
            return

        t_analyze = time.time()
        hue_colors = self.color_analyzer.analyze_zones_batch(zone_colors)
        t_analyze = time.time() - t_analyze
        if not hue_colors or len(hue_colors) == 0:
            return

        t_smooth = time.time()
        smoothed_colors = self.color_analyzer.apply_smoothing(
            hue_colors,
            factor=self.settings.smoothing_factor
        )
        t_smooth = time.time() - t_smooth

        t_update = time.time()
        self._update_lights(smoothed_colors)
        t_update = time.time() - t_update

        total = time.time() - t0

        # Record latest per-stage timings
        with self.lock:
            self._stats['last_stage_times'] = {
                'capture': round(t_capture, 4),
                'zones': round(t_zones, 4),
                'analyze': round(t_analyze, 4),
                'smooth': round(t_smooth, 4),
                'update': round(t_update, 4),
                'total': round(total, 4)
            }

        # Log periodic timing summary to help diagnose bottlenecks
        if self._stats['frame_count'] % 30 == 0:
            _timed_print(f"[timings] capture={self._stats['last_stage_times']['capture']}s zones={self._stats['last_stage_times']['zones']}s analyze={self._stats['last_stage_times']['analyze']}s smooth={self._stats['last_stage_times']['smooth']}s update={self._stats['last_stage_times']['update']}s total={self._stats['last_stage_times']['total']}s")

        # Send RGB colors to GUI for preview, not XY colors
        self._queue_status('status', 'syncing', zone_colors)

    def _update_lights(self, hue_colors: Dict[str, Tuple[Tuple[float, float], int]]):
        """Send color updates via entertainment streaming."""
        if not hue_colors:
            return

        if not self.entertainment_stream or not self.entertainment_stream.is_connected():
            if self._stats['frame_count'] % 300 == 0:
                _timed_print("Warning: Entertainment stream not connected, skipping update")
            return

        # Convert zone colors to channel colors
        channel_colors: Dict[int, Tuple[Tuple[float, float], int]] = {}

        for zone_id, color_data in hue_colors.items():
            channel_id = self._zone_channel_map.get(zone_id)
            if channel_id is None:
                continue

            xy, brightness = color_data

            # If multiple zones map to the same channel, average them
            if channel_id in channel_colors:
                existing_xy, existing_bri = channel_colors[channel_id]
                # Simple average
                new_xy = ((existing_xy[0] + xy[0]) / 2, (existing_xy[1] + xy[1]) / 2)
                new_bri = (existing_bri + brightness) // 2
                channel_colors[channel_id] = (new_xy, new_bri)
            else:
                channel_colors[channel_id] = (xy, brightness)

        # Send to all channels via DTLS
        if channel_colors:
            self.entertainment_stream.send_colors_xy(channel_colors)

    def _queue_status(self, status_type: str, message, data=None):
        """Queue status update for GUI thread."""
        try:
            self.queue.put_nowait((status_type, message, data))
        except queue.Full:
            pass

    def get_status(self) -> Optional[tuple]:
        """Get queued status update."""
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def get_stats(self) -> dict:
        """Get sync statistics."""
        with self.lock:
            return self._stats.copy()

    def reset_stats(self):
        """Reset sync statistics."""
        with self.lock:
            self._stats = {
                'fps': 0,
                'frame_count': 0,
                'errors': 0,
                'last_update': time.time()
            }
