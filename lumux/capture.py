"""Screen capture using PipeWire portal with optimized GStreamer pipeline."""

import time
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
    def __init__(
        self,
        scale_factor: float = 0.125,
        black_bar_settings: Optional["BlackBarSettings"] = None,
        source_type: str = "screen",
    ):
        self.scale_factor = scale_factor
        self.source_type = source_type
        self._display = None

        self._portal_node_id: Optional[int] = None
        self._portal_session_handle: Optional[str] = None
        self._portal_bus = None

        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsink: Optional[GstApp.AppSink] = None
        self._latest_frame: Optional[Image.Image] = None
        self._frame_lock = threading.Lock()
        self._pipeline_running = False
        self._pipeline_error_logged = False

        self._black_bar_detector: Optional[BlackBarDetector] = None
        if black_bar_settings is not None:
            self._init_black_bar_detector(black_bar_settings)

        self._init_display()

    def _init_black_bar_detector(self, settings: "BlackBarSettings") -> None:
        self._black_bar_detector = BlackBarDetector(
            enabled=settings.enabled,
            threshold=settings.threshold,
            detection_rate=settings.detection_rate,
            smooth_factor=settings.smooth_factor
        )

    def update_black_bar_settings(self, settings: "BlackBarSettings") -> None:
        if self._black_bar_detector is None:
            self._init_black_bar_detector(settings)
        else:
            self._black_bar_detector.set_enabled(settings.enabled)
            self._black_bar_detector.set_threshold(settings.threshold)
            self._black_bar_detector.set_detection_rate(settings.detection_rate)
            self._black_bar_detector.smooth_factor = settings.smooth_factor

    def get_black_bar_crop_region(self):
        if self._black_bar_detector is None:
            return None
        return self._black_bar_detector.get_crop_region()

    def _init_display(self):
        try:
            from gi.repository import Gdk
            self._display = Gdk.Display.get_default()
        except Exception as e:
            print(f"Error initializing display: {e}")

    def capture(self) -> Optional[Image.Image]:
        if self._pipeline_running:
            with self._frame_lock:
                frame = self._latest_frame
            if frame:
                return self._process_image(frame.copy())

        if not self._portal_node_id:
            if not self._setup_portal_session():
                return None

        if not self._pipeline_running:
            if not self._start_pipeline():
                return None

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
        if screen is None or screen.width <= 0 or screen.height <= 0:
            return screen

        if self._black_bar_detector is not None:
            try:
                screen = self._black_bar_detector.process(screen)
            except Exception as e:
                print(f"Black bar detection error: {e}")

        if screen is None or screen.width <= 0 or screen.height <= 0:
            return screen

        if self.scale_factor < 1.0:
            new_size = (
                max(1, int(screen.width * self.scale_factor)),
                max(1, int(screen.height * self.scale_factor))
            )
            screen = screen.resize(new_size, Image.Resampling.BILINEAR)
        return screen

    def _setup_portal_session(self) -> bool:
        try:
            import pydbus

            kind = "window" if self.source_type == "window" else "screen"
            print(f"Requesting {kind} capture permission via portal...")
            bus = pydbus.SessionBus()
            self._portal_bus = bus
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

            token = str(int(time.time()))
            req = screencast.CreateSession({"session_handle_token": GLib.Variant("s", "s" + token)})
            sub = bus.con.signal_subscribe(
                None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response
            )
            GLib.timeout_add_seconds(30, loop.quit)
            try:
                loop.run()
            finally:
                bus.con.signal_unsubscribe(sub)

            if not state["session_handle"]:
                return False
            self._portal_session_handle = state["session_handle"]

            portal_types = 1 if self.source_type == "screen" else 2
            loop = GLib.MainLoop()
            req = screencast.SelectSources(self._portal_session_handle, {
                "types": GLib.Variant("u", portal_types),
                "multiple": GLib.Variant("b", False)
            })
            sub = bus.con.signal_subscribe(
                None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response
            )
            try:
                loop.run()
            finally:
                bus.con.signal_unsubscribe(sub)

            loop = GLib.MainLoop()
            req = screencast.Start(self._portal_session_handle, "", {})
            sub = bus.con.signal_subscribe(
                None, "org.freedesktop.portal.Request", "Response", req, None, 0, on_response
            )
            try:
                loop.run()
            finally:
                bus.con.signal_unsubscribe(sub)

            if state["node_id"]:
                self._portal_node_id = state["node_id"]
                print(f"Portal session started. PipeWire node: {self._portal_node_id}")
                return True

        except Exception as e:
            print(f"Failed to setup portal session: {e}")

        return False

    def _get_pipeline_configs(self, node_id: int) -> List[str]:
        configs = []

        has_glupload = Gst.ElementFactory.find('glupload') is not None
        has_glcolorconvert = Gst.ElementFactory.find('glcolorconvert') is not None
        has_gldownload = Gst.ElementFactory.find('gldownload') is not None
        has_glcolorscale = Gst.ElementFactory.find('glcolorscale') is not None

        if has_glupload and has_glcolorconvert and has_gldownload:
            configs.append(
                f'pipewiresrc path={node_id} do-timestamp=true ! '
                f'glupload ! glcolorconvert ! gldownload ! '
                f'video/x-raw,format=RGB ! '
                f'appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
            )

        if has_glupload and has_glcolorscale and has_gldownload:
            configs.append(
                f'pipewiresrc path={node_id} do-timestamp=true ! '
                f'glupload ! glcolorscale ! gldownload ! '
                f'video/x-raw,format=RGB ! '
                f'appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
            )

        if Gst.ElementFactory.find('v4l2convert'):
            configs.append(
                f'pipewiresrc path={node_id} do-timestamp=true ! '
                f'v4l2convert ! '
                f'video/x-raw,format=RGB ! '
                f'appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
            )

        if Gst.ElementFactory.find('videoconvert'):
            configs.append(
                f'pipewiresrc path={node_id} do-timestamp=true ! '
                f'videoconvert ! '
                f'video/x-raw,format=RGB ! '
                f'appsink name=sink emit-signals=true drop=true max-buffers=1 sync=false'
            )

        return configs

    def _start_pipeline(self) -> bool:
        if not self._portal_node_id:
            return False

        configs = self._get_pipeline_configs(self._portal_node_id)
        if not configs:
            print("No suitable GStreamer pipeline configuration found")
            print("Need one of: glupload+glcolorconvert, v4l2convert, or videoconvert")
            self._log_pipeline_details()
            return False

        for i, pipeline_str in enumerate(configs):
            try:
                self._pipeline = Gst.parse_launch(pipeline_str)
                self._appsink = self._pipeline.get_by_name('sink')
                self._appsink.connect('new-sample', self._on_new_sample)

                bus = self._pipeline.get_bus()
                bus.add_signal_watch()
                bus.connect('message::error', self._on_pipeline_error)
                bus.connect('message::warning', self._on_pipeline_warning)
                bus.connect('message::element', self._on_pipeline_element_message)

                ret = self._pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    desc = pipeline_str.split(' ! ')[1] if ' ! ' in pipeline_str else 'unknown'
                    print(f"Pipeline config {i + 1} failed (converter: {desc})")
                    self._pipeline.set_state(Gst.State.NULL)
                    self._pipeline = None
                    continue

                self._pipeline_running = True
                self._pipeline_error_logged = False
                desc = pipeline_str.split(' ! ')[1] if ' ! ' in pipeline_str else 'unknown'
                print(f"GStreamer capture pipeline started (converter: {desc})")
                return True

            except Exception as e:
                print(f"Pipeline config {i + 1} exception: {e}")
                if self._pipeline:
                    self._pipeline.set_state(Gst.State.NULL)
                    self._pipeline = None
                continue

        print("All pipeline configurations failed")
        self._log_pipeline_details()
        return False

    def _on_pipeline_error(self, bus, message):
        err, debug = message.parse_error()
        if not self._pipeline_error_logged:
            print(f"GStreamer pipeline error: {err.message}")
            print(f"GStreamer debug info: {debug}")
            self._pipeline_error_logged = True
        self._pipeline_running = False

    def _on_pipeline_warning(self, bus, message):
        warn, debug = message.parse_warning()
        print(f"GStreamer pipeline warning: {warn.message}")

    def _on_pipeline_element_message(self, bus, message):
        structure = message.get_structure()
        if structure and structure.get_name() == 'missing-plugin':
            print(f"Missing GStreamer plugin: {structure.to_string()}")

    def _log_pipeline_details(self):
        if not self._pipeline:
            return
        try:
            state = self._pipeline.get_state(Gst.CLOCK_TIME_NONE)
            print(f"Pipeline state: {state}")
            print(f"PipeWire node ID: {self._portal_node_id}")
            plugins = {
                'pipewiresrc': Gst.ElementFactory.find('pipewiresrc') is not None,
                'videoconvert': Gst.ElementFactory.find('videoconvert') is not None,
                'v4l2convert': Gst.ElementFactory.find('v4l2convert') is not None,
                'glupload': Gst.ElementFactory.find('glupload') is not None,
                'glcolorconvert': Gst.ElementFactory.find('glcolorconvert') is not None,
                'gldownload': Gst.ElementFactory.find('gldownload') is not None,
                'glcolorscale': Gst.ElementFactory.find('glcolorscale') is not None,
            }
            print(f"GStreamer plugins: {plugins}")
        except Exception as e:
            print(f"Error logging pipeline details: {e}")

    def _on_new_sample(self, appsink) -> Gst.FlowReturn:
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.OK

            buffer = sample.get_buffer()
            caps = sample.get_caps()

            struct = caps.get_structure(0)
            width = struct.get_value('width')
            height = struct.get_value('height')
            fmt = struct.get_value('format') if struct.has_field('format') else None

            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                print(f"Failed to map buffer (format={fmt}, {width}x{height})")
                print("This likely means DMA-BUF buffers are being received.")
                print("Ensure GStreamer GL plugins (gst-plugins-gl) are installed.")
                return Gst.FlowReturn.OK

            try:
                data = bytes(map_info.data)

                if fmt == 'RGB':
                    frame = Image.frombytes('RGB', (width, height), data)
                elif fmt == 'BGR':
                    frame = Image.frombytes('RGB', (width, height), data)
                    r, g, b = frame.split()
                    frame = Image.merge('RGB', (b, g, r))
                elif fmt in ('RGBA', 'RGBx'):
                    frame = Image.frombytes('RGBA', (width, height), data).convert('RGB')
                elif fmt in ('BGRA', 'BGRx'):
                    frame = Image.frombytes('RGBA', (width, height), data).convert('RGB')
                elif fmt == 'BGR15' or fmt == 'RGB15':
                    import numpy as np
                    arr = np.frombuffer(data, dtype=np.uint16).reshape((height, width))
                    r = ((arr >> 10) & 0x1F).astype(np.uint8) * 255 // 31
                    g = ((arr >> 5) & 0x1F).astype(np.uint8) * 255 // 31
                    b = (arr & 0x1F).astype(np.uint8) * 255 // 31
                    frame = Image.fromarray(np.stack([r, g, b], axis=2), 'RGB')
                else:
                    frame = Image.frombytes('RGB', (width, height), data)

                with self._frame_lock:
                    self._latest_frame = frame

            finally:
                buffer.unmap(map_info)

            return Gst.FlowReturn.OK

        except Exception as e:
            print(f"Error processing frame: {e}")
            return Gst.FlowReturn.OK

    def _close_portal_session(self):
        if self._portal_session_handle and self._portal_bus:
            try:
                session = self._portal_bus.get(
                    "org.freedesktop.portal.Desktop",
                    self._portal_session_handle
                )
                session.Close()
                print("Portal session closed")
            except Exception as e:
                print(f"Error closing portal session (may already be closed): {e}")
        self._portal_session_handle = None
        self._portal_bus = None

    def stop_pipeline(self):
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsink = None
            self._pipeline_running = False
            self._latest_frame = None
            self._portal_node_id = None
            print("GStreamer pipeline stopped")
        self._close_portal_session()

    def __del__(self):
        self.stop_pipeline()