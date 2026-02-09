"""Mode manager for switching between Video and Reading modes.

Handles the transition logic between:
- Video Mode: DTLS entertainment streaming (continuous)
- Reading Mode: REST API static color (one-time)

These modes are mutually exclusive - entertainment streaming
must be stopped before using REST API control.
"""

import time
from enum import Enum, auto
from typing import Optional, Tuple, Callable

try:
    from gi.repository import GLib
    HAS_GLIB = True
except ImportError:
    HAS_GLIB = False

from config.settings_manager import ReadingModeSettings
from lumux.hue_bridge import HueBridge
from lumux.sync import SyncController
from lumux.entertainment import EntertainmentStream
from lumux.reading_mode import ReadingModeController
from lumux.utils.logging import timed_print


class Mode(Enum):
    """Available lighting modes."""
    OFF = auto()
    VIDEO = auto()
    READING = auto()


class ModeManager:
    """Manages transitions between video and reading modes.
    
    Ensures proper shutdown of one mode before starting another.
    """
    
    def __init__(self, 
                 bridge: HueBridge,
                 sync_controller: SyncController,
                 entertainment_stream: Optional[EntertainmentStream],
                 reading_mode: ReadingModeSettings = None):
        self.bridge = bridge
        self.sync_controller = sync_controller
        self.entertainment_stream = entertainment_stream
        self.reading_settings = reading_mode
        
        self.current_mode = Mode.OFF
        self._reading_controller: Optional[ReadingModeController] = None
        self._on_mode_changed: Optional[Callable[[Mode], None]] = None
        
        # Track pending reading mode activation to prevent duplicate calls
        self._reading_activation_pending = False
    
    def set_mode_changed_callback(self, callback: Callable[[Mode], None]):
        """Set callback to be called when mode changes."""
        self._on_mode_changed = callback
    
    def _notify_mode_changed(self):
        """Notify listeners of mode change."""
        if self._on_mode_changed:
            self._on_mode_changed(self.current_mode)
    
    def get_reading_controller(self) -> ReadingModeController:
        """Get or create reading mode controller."""
        if self._reading_controller is None:
            self._reading_controller = ReadingModeController(self.bridge)
            # Configure target lights from settings if available
            if self.reading_settings and self.reading_settings.light_ids:
                self._reading_controller.set_target_lights(self.reading_settings.light_ids)
        return self._reading_controller
    
    def switch_to_video(self) -> bool:
        """Switch to video sync mode.
        
        Steps:
        1. Stop reading mode (leave lights as-is or dim)
        2. Deactivate any active entertainment streaming
        3. Activate entertainment configuration
        4. Start DTLS connection
        5. Start sync controller
        
        Returns:
            True if successfully switched to video mode
        """
        timed_print("ModeManager: Switching to VIDEO mode")
        
        # Step 1: Stop reading mode if active
        if self.current_mode == Mode.READING and self._reading_controller:
            timed_print("ModeManager: Stopping reading mode")
            # Don't turn off lights - leave them for smooth transition
            self._reading_controller.deactivate(turn_off=False)
        
        # Step 2: Stop sync if running (shouldn't happen but safety check)
        if self.sync_controller.is_running():
            timed_print("ModeManager: Stopping existing sync")
            self.sync_controller.stop()
        
        # Step 3: Ensure entertainment stream is ready
        if not self.entertainment_stream:
            timed_print("ModeManager: No entertainment stream configured")
            return False
        
        # Step 4: Activate entertainment streaming
        if not self.entertainment_stream.is_connected():
            if not self.bridge.activate_entertainment_streaming(
                self.entertainment_stream.entertainment_config_id
            ):
                timed_print("ModeManager: Failed to activate entertainment streaming")
                return False
            
            # Connect DTLS
            if not self.entertainment_stream.connect(self.bridge):
                timed_print("ModeManager: Failed to connect DTLS")
                self.bridge.deactivate_entertainment_streaming(
                    self.entertainment_stream.entertainment_config_id
                )
                return False
        
        # Step 5: Start video sync
        self.sync_controller.start()
        
        self.current_mode = Mode.VIDEO
        self._notify_mode_changed()
        timed_print("ModeManager: Now in VIDEO mode")
        return True
    
    def switch_to_reading(self, 
                         xy: Optional[Tuple[float, float]] = None,
                         brightness: Optional[int] = None,
                         _callback: Optional[Callable[[bool], None]] = None) -> bool:
        """Switch to reading mode with static color.
        
        Steps:
        1. Stop video sync
        2. Stop DTLS/entertainment streaming  
        3. Deactivate entertainment configuration
        4. Send REST PUT to set static color
        
        Args:
            xy: CIE XY color coordinates (uses settings default if None)
            brightness: Brightness 0-254 (uses settings default if None)
            _callback: Optional callback(result: bool) for async completion
            
        Returns:
            True if successfully switched to reading mode (immediately or scheduled)
        """
        # Prevent duplicate activation calls
        if self._reading_activation_pending:
            timed_print("ModeManager: Reading mode activation already pending, ignoring duplicate call")
            return True
        
        timed_print("ModeManager: Switching to READING mode")
        
        # Use settings defaults if not provided
        if xy is None and self.reading_settings:
            xy = self.reading_settings.color_xy
        if brightness is None and self.reading_settings:
            brightness = self.reading_settings.brightness
        
        # Step 1: Stop video sync if running
        if self.sync_controller.is_running():
            timed_print("ModeManager: Stopping video sync")
            self.sync_controller.stop()
        
        # Step 2: Stop entertainment streaming (disconnect already deactivates)
        if self.entertainment_stream and self.entertainment_stream.is_connected():
            timed_print("ModeManager: Stopping entertainment stream")
            self.entertainment_stream.disconnect(self.bridge)
            # Use non-blocking delay to let bridge process deactivation before REST commands
            if HAS_GLIB:
                self._reading_activation_pending = True
                GLib.timeout_add(1000, self._finish_switch_to_reading, xy, brightness, _callback)
                return True
            else:
                # Fallback for non-GUI contexts
                time.sleep(0.3)
                return self._finish_switch_to_reading(xy, brightness, _callback)
        
        # No delay needed, proceed immediately
        return self._finish_switch_to_reading(xy, brightness, _callback)
    
    def _finish_switch_to_reading(self, 
                                  xy: Optional[Tuple[float, float]], 
                                  brightness: Optional[int],
                                  callback: Optional[Callable[[bool], None]]) -> bool:
        """Complete the reading mode switch after delay.
        
        Returns:
            False to stop GLib timeout, or bool result for synchronous calls
        """
        # Clear pending flag
        self._reading_activation_pending = False
        
        # Check if we were interrupted (e.g., by turn_off)
        if self.current_mode != Mode.OFF:
            timed_print("ModeManager: Reading activation cancelled, mode is no longer OFF")
            if callback:
                callback(False)
            return False
        
        # Activate reading mode via REST
        reading = self.get_reading_controller()
        result = reading.activate(xy=xy, brightness=brightness)
        
        if result:
            self.current_mode = Mode.READING
            self._notify_mode_changed()
            timed_print("ModeManager: Now in READING mode")
        else:
            timed_print("ModeManager: Failed to activate reading mode")
        
        if callback:
            callback(result)
        
        return False  # Always return False for GLib timeout
    
    def turn_off(self, turn_off_lights: bool = True) -> bool:
        """Turn off all lighting control.
        
        Args:
            turn_off_lights: If True, turn off the actual lights
            
        Returns:
            True if successfully turned off
        """
        timed_print("ModeManager: Turning OFF")
        
        # Remember current mode before stopping sync
        mode_before = self.current_mode
        
        # Check if reading mode activation is pending (non-blocking transition)
        # If so, cancel it to prevent race conditions
        if self._reading_activation_pending:
            timed_print("ModeManager: Cancelling pending reading mode activation")
            self._reading_activation_pending = False
        
        # Stop video sync (this may trigger auto-activation callback)
        if self.sync_controller.is_running():
            self.sync_controller.stop()
        
        # Check if auto-activation already switched us to reading mode
        # In that case, don't turn off - let reading mode stay active
        if mode_before == Mode.VIDEO and self.current_mode == Mode.READING:
            timed_print("ModeManager: Auto-activated reading mode, staying in READING mode")
            return True
        
        # Stop entertainment stream
        if self.entertainment_stream and self.entertainment_stream.is_connected():
            self.entertainment_stream.disconnect(self.bridge)
        
        # Stop reading mode
        if self._reading_controller and self._reading_controller.is_active():
            self._reading_controller.deactivate(turn_off=turn_off_lights)
        
        self.current_mode = Mode.OFF
        self._notify_mode_changed()
        timed_print("ModeManager: Now OFF")
        return True
    
    def is_video_active(self) -> bool:
        """Check if video mode is currently active."""
        return self.current_mode == Mode.VIDEO and self.sync_controller.is_running()
    
    def is_reading_active(self) -> bool:
        """Check if reading mode is currently active."""
        return self.current_mode == Mode.READING and (
            self._reading_controller is not None and self._reading_controller.is_active()
        )
    
    def get_current_mode(self) -> Mode:
        """Get current mode."""
        return self.current_mode
    
    def on_video_sync_stopped(self) -> bool:
        """Called when video sync stops (e.g., user clicked Stop).
        
        If auto_activate is enabled, automatically switch to reading mode.
        
        Returns:
            True if auto-switched to reading mode
        """
        if self.current_mode != Mode.VIDEO:
            return False
        
        self.current_mode = Mode.OFF  # Temporary state
        
        # Check if we should auto-activate reading mode
        if self.reading_settings and self.reading_settings.auto_activate:
            timed_print("ModeManager: Video stopped, auto-activating reading mode")
            return self.switch_to_reading()
        
        self._notify_mode_changed()
        return False
