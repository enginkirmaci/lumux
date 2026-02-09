"""Reading Mode controller using REST API.

Unlike video mode which uses continuous DTLS streaming,
reading mode sends one-time PUT requests via REST API.
The bridge maintains the light state until changed.
"""

from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from lumux.hue_bridge import HueBridge
from lumux.utils.logging import timed_print


@dataclass
class ReadingModeState:
    """Current reading mode state."""
    is_active: bool = False
    color_xy: Tuple[float, float] = (0.5, 0.4)
    brightness: int = 150


class ReadingModeController:
    """Manages static color lighting via REST API.
    
    Uses one-time PUT requests to set light color/brightness.
    No continuous streaming needed - bridge maintains state.
    """
    
    def __init__(self, bridge: HueBridge):
        self.bridge = bridge
        self._state = ReadingModeState()
        self._target_light_ids: List[str] = []
    
    def set_target_lights(self, light_ids: List[str]):
        """Set which lights to control in reading mode.
        
        If empty, will try to use lights from the entertainment zone.
        """
        self._target_light_ids = light_ids.copy()
    
    def activate(self, xy: Optional[Tuple[float, float]] = None, 
                 brightness: Optional[int] = None,
                 transition_ms: int = 400) -> bool:
        """Activate reading mode with static color.
        
        Sends one-time PUT request to all target lights.
        Bridge maintains this state until changed.
        
        Args:
            xy: CIE XY color coordinates (x, y), each 0.0-1.0
            brightness: Brightness 0-254
            transition_ms: Transition time in milliseconds
            
        Returns:
            True if all lights were updated successfully
        """
        if xy is not None:
            self._state.color_xy = xy
        if brightness is not None:
            self._state.brightness = brightness
        
        # Ensure bridge devices are refreshed before getting lights
        if hasattr(self.bridge, 'refresh_devices'):
            try:
                self.bridge.refresh_devices()
            except Exception as e:
                timed_print(f"Reading mode: Could not refresh devices: {e}")
        
        # Get lights to control
        light_ids = self._get_target_light_ids()
        if not light_ids:
            timed_print("Reading mode: No lights to control")
            return False
        
        timed_print(f"Reading mode: Activating with xy={self._state.color_xy}, "
                   f"brightness={self._state.brightness} for {len(light_ids)} lights")
        
        success_count = 0
        for light_id in light_ids:
            try:
                self.bridge.set_light_color(
                    light_id=light_id,
                    xy=self._state.color_xy,
                    brightness=self._state.brightness,
                    transition_time=transition_ms
                )
                success_count += 1
            except Exception as e:
                timed_print(f"Reading mode: Failed to set light {light_id}: {e}")
        
        self._state.is_active = success_count > 0
        
        if success_count == len(light_ids):
            timed_print(f"Reading mode: Activated successfully for all {len(light_ids)} lights")
            return True
        elif success_count > 0:
            timed_print(f"Reading mode: Partial success - {success_count}/{len(light_ids)} lights")
            return True
        else:
            timed_print("Reading mode: Failed to activate")
            return False
    
    def deactivate(self, turn_off: bool = False) -> bool:
        """Deactivate reading mode.
        
        Args:
            turn_off: If True, turn lights off. If False, leave at current state.
            
        Returns:
            True if operation succeeded
        """
        if not self._state.is_active:
            return True
        
        if turn_off:
            light_ids = self._get_target_light_ids()
            timed_print(f"Reading mode: Turning off {len(light_ids)} lights")
            
            for light_id in light_ids:
                try:
                    # Turn light off via bridge client
                    if self.bridge.client:
                        self.bridge.client.set_light_state(light_id, {'on': {'on': False}})
                except Exception as e:
                    timed_print(f"Reading mode: Failed to turn off light {light_id}: {e}")
        
        self._state.is_active = False
        timed_print("Reading mode: Deactivated")
        return True
    
    def update_color(self, xy: Tuple[float, float], 
                     brightness: Optional[int] = None,
                     transition_ms: int = 200) -> bool:
        """Update color/brightness while already in reading mode.
        
        Args:
            xy: New CIE XY color coordinates
            brightness: New brightness 0-254 (optional)
            transition_ms: Transition time in milliseconds
            
        Returns:
            True if update succeeded
        """
        self._state.color_xy = xy
        if brightness is not None:
            self._state.brightness = brightness
        
        if not self._state.is_active:
            # If not active, just update state - don't send
            return True
        
        return self.activate(transition_ms=transition_ms)
    
    def is_active(self) -> bool:
        """Check if reading mode is currently active."""
        return self._state.is_active
    
    def get_state(self) -> ReadingModeState:
        """Get current reading mode state."""
        return ReadingModeState(
            is_active=self._state.is_active,
            color_xy=self._state.color_xy,
            brightness=self._state.brightness
        )
    
    def _get_target_light_ids(self) -> List[str]:
        """Get list of light IDs to control.
        
        Returns explicit targets if set, otherwise tries to discover
        lights from entertainment configuration.
        """
        if self._target_light_ids:
            return self._target_light_ids
        
        # Try to get lights from entertainment config
        config_id = self.bridge.settings.hue.entertainment_config_id if hasattr(self.bridge, 'settings') else None
        if not config_id and hasattr(self.bridge, 'app_context'):
            config_id = self.bridge.app_context.settings.hue.entertainment_config_id
        
        if config_id:
            try:
                config = self.bridge.get_entertainment_configuration(config_id)
                if config and 'channels' in config:
                    light_ids = []
                    for channel in config['channels']:
                        for member in channel.get('members', []):
                            service = member.get('service', {})
                            if service.get('rtype') == 'light':
                                light_ids.append(service['rid'])
                    if light_ids:
                        return light_ids
            except Exception as e:
                timed_print(f"Reading mode: Failed to get lights from entertainment config: {e}")
        
        # Fallback: use all known lights
        if hasattr(self.bridge, 'get_light_ids'):
            return self.bridge.get_light_ids()
        
        return []
