"""Screen capture using PipeWire portal with optimized GStreamer pipeline."""

import time
import os
import threading
from typing import Optional, List, TYPE_CHECKING

import PIL.Image as Image

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import GLib, Gst, GstApp

from lumux.black_bar_detector import BlackBarDetector

if TYPE_CHECKING:
    from config.settings_manager import BlackBarSettings

Gst.init(None)


class ScreenCapture:
    def __init__(self, scale_factor: float = 0.125, black_bar_settings: Optional["BlackBarSettings"] = None):
        self.scale_factor = scale_factor
        self._display = None
        
        # Portal state
        self._portal_node_id: Optional[int] = None
        self._portal_session_handle: Optional[str] = None
        
        # GStreamer pipeline for high-performance capture
        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsink: Optional[GstApp.AppSink] = None
        self._latest_frame: Optional[Image.Image] = None
        self._frame_lock = threading.Lock()
        self._pipeline_running = False
        
        # Black bar detector for letterbox/pillarbox removal
        self._black_bar_detector: Optional[BlackBarDetector] = None
        if black_bar_settings is not None:
            self._init_black_bar_detector(black_bar_settings)
        
        self._init_display()
    
    def _init_black_bar_detector(self, settings: "BlackBarSettings") -> None:
        """Initialize black bar detector from settings."""
        self._black_bar_detector = BlackBarDetector(
            enabled=settings.enabled,
            threshold=settings.threshold,
            detection_rate=settings.detection_rate,
            smooth_factor=settings.smooth_factor
        )
    
    def update_black_bar_settings(self, settings: "BlackBarSettings") -> None:
        """Update black bar detector settings dynamically."""
        if self._black_bar_detector is None:
            self._init_black_bar_detector(settings)
        else:
            self._black_bar_detector.set_enabled(settings.enabled)
            self._black_bar_detector.set_threshold(settings.threshold)
            self._black_bar_detector.set_detection_rate(settings.detection_rate)
            self._black_bar_detector.smooth_factor = settings.smooth_factor
    
    def get_black_bar_crop_region(self):
        """Get current black bar crop region (for zone processing alignment).
        
        Returns:
            CropRegion or None if no cropping applied
        """
        if self._black_bar_detector is None:
            return None
        return self._black_bar_detector.get_crop_region()

    def _init_display(self):
        """Initialize Gdk display for monitor info."""
        try:
            # Import Gdk lazily - it's already loaded with version 4.0 from GUI
            from gi.repository import Gdk
            self._display = Gdk.Display.get_default()
            # Display index removed; we only keep a reference to the display
        except Exception as e:
            print(f"Error initializing display: {e}")

    def capture(self) -> Optional[Image.Image]:
        """Capture screen using portal pipeline."""
        # If pipeline is running, grab latest frame
        if self._pipeline_running:
            with self._frame_lock:
                frame = self._latest_frame
            if frame:
                return self._process_image(frame.copy())
        
        # Setup portal and start pipeline if not running
        if not self._portal_node_id:
            if not self._setup_portal_session():
                return None
        
        if not self._pipeline_running:
            if not self._start_pipeline():
                return None
        
        # Wait for first frame with timeout
        timeout = 2.0
        start = time.time()
        while (time.time() - start) < timeout:
            with self._frame_lock:
                frame = self._latest_frame
            if frame:
                return self._process_image(frame.copy())
            time.sleep(0.01)
        
        return None

    def _process_image(self, screen: Image.Image) -> Image.Image:
        """Apply scaling and black bar detection to image if needed."""
        # Safety check for invalid input
        if screen is None or screen.width <= 0 or screen.height <= 0:
            return screen
        
        # Apply black bar detection first (on full resolution for accuracy)
        if self._black_bar_detector is not None:
            try:
                screen = self._black_bar_detector.process(screen)
            except Exception as e:
                print(f"Black bar detection error: {e}")
                # Continue with original image on error
        
        # Safety check after black bar processing
        if screen is None or screen.width <= 0 or screen.height <= 0:
            return screen
        
        # Apply Scaling - use BILINEAR for speed (LANCZOS is too slow)
        if self.scale_factor < 1.0:
            new_size = (
                max(1, int(screen.width * self.scale_factor)),
                max(1, int(screen.height * self.scale_factor))
            )
            screen = screen.resize(new_size, Image.Resampling.BILINEAR)
        return screen

    def _setup_portal_session(self) -> bool:
        """Initialize XDG Desktop Portal ScreenCast session."""
        try:
            import pydbus
            
            print("Requesting screen capture permission via portal...")
            bus = pydbus.SessionBus()
            portal = bus.get("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
            screencast = portal["org.freedesktop.portal.ScreenCast"]
            
            loop = GLib.MainLoop()
            state = {"session_handle": None, "node_id": None, "error": None}

            def on_response(connection, sender, object, interface, signal, params):
                code, results = params
                if code != 0:
                    state["error"] = code
                    loop.quit()
                    return
                
                if "session_handle" in results:
                    state["session_handle"] = results["session_handle"]
                    loop.quit()
                elif "streams" in results:
                    state["node_id"] = results["streams"][0][0]
                    loop.quit()
                else:
                    loop.quit()

            # 1. CreateSession
            token = str(int(time.time()))
            req = screencast.CreateSession({"session_handle_token": GLib.Variant("s", "s"+token)})
            sub = bus.con.signal_subscribe(None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response)
            GLib.timeout_add_seconds(30, loop.quit)
            loop.run()
            bus.con.signal_unsubscribe(sub)
            
            if not state["session_handle"]:
                return False
            self._portal_session_handle = state["session_handle"]

            # 2. SelectSources
            loop = GLib.MainLoop()
            req = screencast.SelectSources(self._portal_session_handle, {
                "types": GLib.Variant("u", 1),  # Monitor
                "multiple": GLib.Variant("b", False)
            })
            sub = bus.con.signal_subscribe(None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response)
            loop.run()
            bus.con.signal_unsubscribe(sub)
            
            # 3. Start
            loop = GLib.MainLoop()
            req = screencast.Start(self._portal_session_handle, "", {})
            sub = bus.con.signal_subscribe(None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response)
            loop.run()
            bus.con.signal_unsubscribe(sub)
            
            if state["node_id"]:
                self._portal_node_id = state["node_id"]
                print(f"Portal session started. PipeWire node: {self._portal_node_id}")
                return True
                
        except Exception as e:
            print(f"Failed to setup portal session: {e}")
            
        return False

    def _start_pipeline(self) -> bool:
        """Start GStreamer pipeline for continuous capture."""
        if not self._portal_node_id:
            return False
        
        try:
            # Build optimized pipeline:
            # - pipewiresrc: capture from portal
            # - videoconvert: convert to RGB
            # - appsink: get frames directly in memory (no file I/O!)
            # drop=true ensures we always get latest frame, max-buffers=1 keeps memory low
            pipeline_str = (
                f'pipewiresrc path={self._portal_node_id} do-timestamp=true ! '
                f'videoconvert ! '
                f'video/x-raw,format=RGB ! '
                f'appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
            )
            
            self._pipeline = Gst.parse_launch(pipeline_str)
            self._appsink = self._pipeline.get_by_name('sink')
            
            # Connect to new-sample signal for frame callback
            self._appsink.connect('new-sample', self._on_new_sample)
            
            # Start pipeline
            ret = self._pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print("Failed to start GStreamer pipeline")
                return False
            
            self._pipeline_running = True
            print("GStreamer capture pipeline started (high-performance mode)")
            return True
            
        except Exception as e:
            print(f"Failed to start pipeline: {e}")
            return False

    def _on_new_sample(self, appsink) -> Gst.FlowReturn:
        """Handle new frame from GStreamer pipeline."""
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.OK
            
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            # Extract frame dimensions from caps
            struct = caps.get_structure(0)
            width = struct.get_value('width')
            height = struct.get_value('height')
            
            # Map buffer to get raw bytes
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.OK
            
            try:
                # Create PIL Image from raw RGB data
                frame = Image.frombytes('RGB', (width, height), bytes(map_info.data))
                
                with self._frame_lock:
                    self._latest_frame = frame
                    
            finally:
                buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            print(f"Error processing frame: {e}")
            return Gst.FlowReturn.OK

    def stop_pipeline(self):
        """Stop the GStreamer pipeline."""
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsink = None
            self._pipeline_running = False
            self._latest_frame = None
            self._portal_node_id = None
            self._portal_session_handle = None
            print("GStreamer pipeline stopped")

    def __del__(self):
        """Cleanup on destruction."""
        self.stop_pipeline()
