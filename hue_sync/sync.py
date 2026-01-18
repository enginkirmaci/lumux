"""Main sync controller with threading."""

import queue
import threading
import time
from typing import Dict, Tuple, Optional

from hue_sync.bridge import HueBridge
from hue_sync.capture import ScreenCapture
from hue_sync.zones import ZoneProcessor
from hue_sync.colors import ColorAnalyzer
from config.zone_mapping import ZoneMapping
from typing import Optional


class SyncController:
    def __init__(self, bridge: HueBridge, capture: ScreenCapture,
                 zone_processor: ZoneProcessor, color_analyzer: ColorAnalyzer,
                 zone_mapping: ZoneMapping, settings, light_updater: Optional[object] = None):
        self.bridge = bridge
        self.capture = capture
        self.zone_processor = zone_processor
        self.color_analyzer = color_analyzer
        self.zone_mapping = zone_mapping
        self.settings = settings
        self.light_updater = light_updater

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.previous_colors: Dict[str, Tuple[Tuple[float, float], int]] = {}
        self.queue: queue.Queue = queue.Queue(maxsize=100)
        self.lock = threading.Lock()

        self._stats = {
            'fps': 0,
            'frame_count': 0,
            'errors': 0,
            'last_update': time.time()
        }

    def start(self):
        """Start sync thread."""
        if self.running:
            return
        
        # Check if existing mapping is valid
        available_lights = self.bridge.get_light_ids()
        is_stale = False
        
        # 1. Check if lights in mapping still exist
        mapping_lights = set()
        for lights in self.zone_mapping.mapping.values():
            for l in lights: mapping_lights.add(l)
        
        if mapping_lights and not any(l in available_lights for l in mapping_lights):
            is_stale = True
            
        # 2. Check if gradient lights are properly mapped to multiple zones
        # If a light is a gradient light but only appears in 1 zone total, it's poorly mapped
        if not is_stale and available_lights:
            for lid in available_lights:
                info = self.bridge.light_info.get(lid, {})
                if info.get('is_gradient'):
                    # Count how many zones this light is in
                    zone_count = sum(1 for lights in self.zone_mapping.mapping.values() if lid in lights)
                    if zone_count <= 1:
                        print(f"Gradient light {lid} ('{info.get('name')}') is under-mapped ({zone_count} zone), forcing regeneration...")
                        is_stale = True
                        break

        # Auto-generate zone mapping if empty or stale
        if not any(self.zone_mapping.mapping.values()) or is_stale:
            if is_stale:
                self.zone_mapping.mapping = {}

            print(f"Generating mapping for layout: {self.zone_processor.layout}")
            if available_lights:
                if self.zone_processor.layout == "ambilight":
                    self.zone_mapping.generate_ambilight_mapping(
                        available_lights,
                        light_info=self.bridge.light_info,
                        top_count=self.zone_processor.cols,
                        bottom_count=self.zone_processor.cols,
                        left_count=max(1, self.zone_processor.rows // 2),
                        right_count=max(1, self.zone_processor.rows // 2)
                    )
                else:
                    self.zone_mapping.generate_grid_mapping(
                        available_lights,
                        self.zone_processor.rows,
                        self.zone_processor.cols
                    )
                
                if self.zone_mapping.mapping_file:
                    self.zone_mapping.save(self.zone_mapping.mapping_file)
                    print(f"Saved mapping to {self.zone_mapping.mapping_file}")

                print(f"Active mapping for {len(available_lights)} lights:")
                for lid in available_lights:
                    m_zones = [z for z, lits in self.zone_mapping.mapping.items() if lid in lits]
                    print(f"  Light '{self.bridge.get_light_name(lid)}' -> {len(m_zones)} zones")
            else:
                print("Warning: No lights available on bridge")

        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True, name="SyncLoop")
        self.thread.start()

    def stop(self):
        """Stop sync thread."""
        if not self.running:
            return

        self.running = False
        
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                print("Warning: Sync thread did not stop cleanly")
        
        # Stop the capture pipeline to release portal session
        if hasattr(self.capture, 'stop_pipeline'):
            self.capture.stop_pipeline()

        # Stop light updater if present
        try:
            if getattr(self, 'light_updater', None):
                self.light_updater.stop()
        except Exception:
            pass

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
                    print(f"Sync target FPS={fps_target}, target_delay={target_delay:.4f}s, measured_fps={self._stats['fps']:.1f}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                self._stats['errors'] += 1
                print(f"Sync loop error: {e}")
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
            print(f"[timings] capture={self._stats['last_stage_times']['capture']}s zones={self._stats['last_stage_times']['zones']}s analyze={self._stats['last_stage_times']['analyze']}s smooth={self._stats['last_stage_times']['smooth']}s update={self._stats['last_stage_times']['update']}s total={self._stats['last_stage_times']['total']}s")

        # Send RGB colors to GUI for preview, not XY colors
        self._queue_status('status', 'syncing', zone_colors)

    def _update_lights(self, hue_colors: Dict[str, Tuple[Tuple[float, float], int]]):
        """Send color updates to Hue bridge."""
        if not hue_colors:
            return
            
        transition_time = self.settings.transition_time_ms
        updated_count = 0

        # Create a mapping of light_id -> list of colors from mapped zones
        light_updates = {}
        for zone_id, color_data in hue_colors.items():
            light_ids = self.zone_mapping.get_lights_for_zone(zone_id)
            for lid in light_ids:
                if lid not in light_updates:
                    light_updates[lid] = []
                # Keep track of which zone this color came from for gradient mapping
                light_updates[lid].append((zone_id, color_data))

        for light_id, updates in light_updates.items():
            info = self.bridge.light_info.get(light_id, {})
            is_gradient = info.get('is_gradient', False)
            
            try:
                if is_gradient:
                    # Handle gradient light
                    points_count = info.get('gradient_points', 3)
                    if points_count == 0: points_count = 3 # Default to 3
                    
                    # Map zones to gradient points
                    # For PC lightstrip: [Left, Top, Right] or similar
                    # We'll try to sort updates by zone type (left, top, right, bottom)
                    
                    # Sort updates to ensure deterministic mapping: left -> top -> right -> bottom
                    def zone_order(item):
                        zid = item[0]
                        try:
                            edge, idx_str = zid.split('_')
                            idx = int(idx_str)
                        except:
                            return (9, 0)
                        
                        # Recommended order for PC lightstrip (starts bottom-left, goes clockwise):
                        # 1. Left edge: index 0 (top) down to index N (bottom) - wait, let's reverse for wrap
                        # In ZoneProcessor, left_0 is TOP, left_N is BOTTOM.
                        # So for wrap starting at bottom-left:
                        if edge == 'left': return (0, -idx) # reverse: bottom-to-top
                        if edge == 'top': return (1, idx)   # left-to-right
                        if edge == 'right': return (2, idx) # top-to-bottom
                        if edge == 'bottom': return (3, -idx) # right-to-left
                        return (4, idx)
                    
                    sorted_updates = sorted(updates, key=zone_order)
                    
                    fixed_points = []
                    # Distribute the available zone colors across the supported gradient points
                    for i in range(points_count):
                        # Pick the best available zone color for this point
                        idx = int(i * len(sorted_updates) / points_count)
                        z_id, (xy, br) = sorted_updates[idx]
                        fixed_points.append({
                            'color': {'xy': {'x': xy[0], 'y': xy[1]}},
                            'dimming': {'brightness': (br / 254.0) * 100.0}
                        })
                    
                    # Use average brightness for the overall light level
                    avg_brightness = sum(u[1][1] for u in updates) / len(updates)
                    
                    if self._stats['frame_count'] % 100 == 0:
                        print(f"Sending gradient update for '{info.get('name')}' ({points_count} points, from {len(sorted_updates)} zones)")

                    payload = {
                        'type': 'gradient',
                        'fixed_points': fixed_points,
                        'brightness': int(avg_brightness)
                    }

                    if self.light_updater:
                        self.light_updater.enqueue(light_id, payload)
                    else:
                        self.bridge.set_light_gradient(light_id, fixed_points, int(avg_brightness))
                else:
                    # Normal light - use the first (or average) color
                    xy, brightness = updates[0][1]
                    payload = {
                        'type': 'color',
                        'xy': xy,
                        'brightness': brightness,
                        'transition_time': transition_time
                    }

                    if self.light_updater:
                        self.light_updater.enqueue(light_id, payload)
                    else:
                        self.bridge.set_light_color(
                            light_id, xy, brightness,
                            transition_time=transition_time
                        )
                
                updated_count += 1
            except Exception as e:
                print(f"Error updating light {light_id}: {e}")
        
        if updated_count == 0:
            print(f"Warning: No lights updated. Zone mapping may be empty.")

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
