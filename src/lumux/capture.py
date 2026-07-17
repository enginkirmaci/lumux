"""Screen capture using PipeWire portal with optimized GStreamer pipeline."""

import re
import time
import threading
from typing import Optional, List, Set, TYPE_CHECKING

import numpy as np

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import GLib, Gst, GstApp, GstVideo

from lumux.black_bar_detector import BlackBarDetector, CropRegion

if TYPE_CHECKING:
    from lumux.config.settings_manager import BlackBarSettings

Gst.init(None)


class ScreenCapture:
    def __init__(
        self,
        scale_factor: float = 0.125,
        black_bar_settings: Optional["BlackBarSettings"] = None,
        source_type: str = "screen",
        restore_token: str = "",
    ):
        self.scale_factor = scale_factor
        self.source_type = source_type
        self._display = None

        self._portal_node_id: Optional[int] = None
        self._portal_session_handle: Optional[str] = None
        self._portal_bus = None
        # Portal restore token for persistent screen-cast consent. When set,
        # the portal can skip the permission dialog on subsequent sessions.
        self._restore_token: str = restore_token or ""
        self._on_restore_token_changed = None
        if self._restore_token:
            print(
                f"[capture] Loaded cached screen-share consent token "
                f"({len(self._restore_token)} chars) — should skip prompt"
            )
        else:
            print("[capture] No cached consent token — permission dialog will be shown")

        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsink: Optional[GstApp.AppSink] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_data: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._pipeline_running = False
        self._pipeline_error_logged = False
        self._runtime_failed_configs: Set[str] = set()
        self._active_config_key: Optional[str] = None

        self._source_width: Optional[int] = None
        self._source_height: Optional[int] = None
        self._pipeline_scaled = False
        self._needs_pipeline_restart = False

        self._black_bar_detector: Optional[BlackBarDetector] = None
        if black_bar_settings is not None:
            self._init_black_bar_detector(black_bar_settings)

        self._init_display()

    def _compute_scaled_dimensions(self):
        if self._source_width and self._source_height and self.scale_factor < 1.0:
            # Round down to a multiple of 4 so RGB row strides stay 4-byte
            # aligned (avoids padded strides) and odd-width caps that some
            # converters refuse to link.
            w = max(4, int(self._source_width * self.scale_factor) & ~3)
            h = max(4, int(self._source_height * self.scale_factor) & ~3)
            return w, h
        return None, None

    def update_scale_factor(self, new_scale: float) -> None:
        new_scale = max(0.01, min(1.0, new_scale))
        changed = abs(new_scale - self.scale_factor) > 0.001
        self.scale_factor = new_scale
        if changed and self._pipeline_running:
            target_w, target_h = self._compute_scaled_dimensions()
            scaled_changed = target_w != getattr(
                self, "_scaled_w", None
            ) or target_h != getattr(self, "_scaled_h", None)
            if scaled_changed:
                self._restart_pipeline()

    def _stop_gst_pipeline(self) -> None:
        if self._pipeline:
            bus = self._pipeline.get_bus()
            if bus:
                bus.remove_signal_watch()
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsink = None
        self._active_config_key = None
        self._pipeline_running = False
        self._latest_frame = None
        self._latest_frame_data = None

    def _restart_pipeline(self) -> None:
        self._needs_pipeline_restart = False
        self._stop_gst_pipeline()
        if self._portal_node_id:
            self._start_pipeline()

    def _init_black_bar_detector(self, settings: "BlackBarSettings") -> None:
        self._black_bar_detector = BlackBarDetector(
            enabled=settings.enabled,
            threshold=settings.threshold,
            detection_rate=settings.detection_rate,
            smooth_factor=settings.smooth_factor,
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

    @property
    def restore_token(self) -> str:
        """Current portal restore token (for diagnostics)."""
        return self._restore_token

    def set_on_restore_token_changed(self, callback) -> None:
        """Register a callback invoked when the portal issues/refreshes a
        restore token. Signature: callback(token: str). Use it to persist the
        token so subsequent runs can skip the permission dialog.
        """
        self._on_restore_token_changed = callback

    def capture(self) -> Optional[np.ndarray]:
        if self._needs_pipeline_restart and self._pipeline_running:
            self._restart_pipeline()
            if not self._pipeline_running:
                return None

        if self._pipeline_running:
            with self._frame_lock:
                frame = self._latest_frame
            if frame is not None:
                return self._process_image(frame)

        if not self._portal_node_id:
            if not self._setup_portal_session():
                # A stale restore token (e.g. after a monitor/source change)
                # can make session setup fail silently. Retry once without it
                # so the portal shows a fresh permission dialog.
                if self._restore_token:
                    print(
                        "[capture] Cached consent token was rejected by portal "
                        "(stale or revoked) — clearing cache and re-prompting"
                    )
                    self._restore_token = ""
                    if self._on_restore_token_changed:
                        try:
                            self._on_restore_token_changed("")
                        except Exception as e:
                            print(f"Error clearing restore token: {e}")
                    if not self._setup_portal_session():
                        return None
                else:
                    return None

        if not self._pipeline_running:
            if not self._start_pipeline():
                return None

        timeout = 2.0
        start = time.time()
        while (time.time() - start) < timeout:
            with self._frame_lock:
                frame = self._latest_frame
            if frame is not None:
                return self._process_image(frame)
            time.sleep(0.01)

        return None

    def _process_image(self, screen: np.ndarray) -> np.ndarray:
        if screen is None or screen.size == 0:
            return screen

        if self._black_bar_detector is not None:
            try:
                crop_region = self._black_bar_detector.process(screen)
                if crop_region is not None and crop_region.is_valid(
                    screen.shape[1], screen.shape[0]
                ):
                    screen = screen[
                        crop_region.top : crop_region.bottom,
                        crop_region.left : crop_region.right,
                        :,
                    ]
            except Exception as e:
                print(f"Black bar detection error: {e}")

        if screen is None or screen.size == 0:
            return screen

        if not self._pipeline_scaled and self.scale_factor < 1.0:
            import PIL.Image as Image

            new_h = max(1, int(screen.shape[0] * self.scale_factor))
            new_w = max(1, int(screen.shape[1] * self.scale_factor))
            if not screen.flags["C_CONTIGUOUS"]:
                screen = np.ascontiguousarray(screen)
            screen = np.array(
                Image.fromarray(screen).resize(
                    (new_w, new_h), Image.Resampling.BILINEAR
                )
            )
        return screen

    def _setup_portal_session(self) -> bool:
        try:
            import pydbus

            kind = "window" if self.source_type == "window" else "screen"
            print(f"Requesting {kind} capture permission via portal...")
            bus = pydbus.SessionBus()
            self._portal_bus = bus
            portal = bus.get(
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
            )
            screencast = portal["org.freedesktop.portal.ScreenCast"]

            loop = GLib.MainLoop()
            state = {
                "session_handle": None,
                "node_id": None,
                "restore_token": None,
                "error": None,
            }

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
                    # The Start response may carry a restore_token when
                    # persistent consent was granted; persist it for next time.
                    state["restore_token"] = results.get("restore_token", "")
                    loop.quit()
                else:
                    loop.quit()

            token = str(int(time.time()))
            create_options = {
                "session_handle_token": GLib.Variant("s", "s" + token),
                # persist_mode = 2: persist consent until explicitly revoked,
                # so the portal can issue a restore_token for future sessions.
                "persist_mode": GLib.Variant("u", 2),
            }
            # Only send a restore_token when we actually have one; sending an
            # empty string can confuse some portal backends.
            if self._restore_token:
                create_options["restore_token"] = GLib.Variant(
                    "s", self._restore_token
                )
                print(
                    "[capture] Restoring cached screen-share consent "
                    f"(token length {len(self._restore_token)}) — "
                    "dialog should be skipped"
                )
            else:
                print(
                    "[capture] Requesting fresh screen-share consent "
                    "(persist_mode=2) — dialog will be shown once"
                )
            req = screencast.CreateSession(create_options)
            sub = bus.con.signal_subscribe(
                None,
                "org.freedesktop.portal.Request",
                "Response",
                req,
                None,
                0,
                on_response,
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
            req = screencast.SelectSources(
                self._portal_session_handle,
                {
                    "types": GLib.Variant("u", portal_types),
                    "multiple": GLib.Variant("b", False),
                },
            )
            sub = bus.con.signal_subscribe(
                None,
                "org.freedesktop.portal.Request",
                "Response",
                req,
                None,
                0,
                on_response,
            )
            try:
                loop.run()
            finally:
                bus.con.signal_unsubscribe(sub)

            loop = GLib.MainLoop()
            req = screencast.Start(self._portal_session_handle, "", {})
            sub = bus.con.signal_subscribe(
                None,
                "org.freedesktop.portal.Request",
                "Response",
                req,
                None,
                0,
                on_response,
            )
            try:
                loop.run()
            finally:
                bus.con.signal_unsubscribe(sub)

            if state["node_id"]:
                self._portal_node_id = state["node_id"]
                print(f"Portal session started. PipeWire node: {self._portal_node_id}")
                # Persist/refresh the restore token if the portal granted one.
                new_token = state.get("restore_token") or ""
                if new_token:
                    print(
                        f"[capture] Screen-share consent cached "
                        f"(token length {len(new_token)}) — "
                        "will skip prompt on next sync"
                    )
                else:
                    print(
                        "[capture] Portal did NOT issue a consent token — "
                        "host does not support persisting screen-share consent "
                        "(needs GNOME 47+ / Plasma 6.x), so the prompt will "
                        "recur each sync"
                    )
                if new_token != self._restore_token:
                    self._restore_token = new_token
                    if self._on_restore_token_changed:
                        try:
                            self._on_restore_token_changed(new_token)
                        except Exception as e:
                            print(f"Error persisting restore token: {e}")
                return True

        except Exception as e:
            print(f"Failed to setup portal session: {e}")

        return False

    def _get_pipeline_configs(self, node_id: int) -> List[str]:
        configs = []

        target_w, target_h = self._compute_scaled_dimensions()

        has_glupload = Gst.ElementFactory.find("glupload") is not None
        has_glcolorconvert = Gst.ElementFactory.find("glcolorconvert") is not None
        has_gldownload = Gst.ElementFactory.find("gldownload") is not None
        has_glcolorscale = Gst.ElementFactory.find("glcolorscale") is not None
        has_videoscale = Gst.ElementFactory.find("videoscale") is not None
        has_v4l2convert = Gst.ElementFactory.find("v4l2convert") is not None
        has_videoconvert = Gst.ElementFactory.find("videoconvert") is not None

        sink_props = "name=sink emit-signals=true drop=true max-buffers=1 sync=false"
        src = f"pipewiresrc path={node_id} do-timestamp=true"

        if target_w and target_h:
            scaled_caps = f"video/x-raw,format=RGB,width={target_w},height={target_h}"

            if has_glupload and has_glcolorconvert and has_gldownload:
                if has_glcolorscale:
                    configs.append(
                        f"{src} ! "
                        f"glupload ! glcolorconvert ! glcolorscale ! "
                        f"gldownload ! videoscale ! {scaled_caps} ! "
                        f"appsink {sink_props}"
                    )
                if has_videoscale:
                    configs.append(
                        f"{src} ! "
                        f"glupload ! glcolorconvert ! gldownload ! videoscale ! "
                        f"{scaled_caps} ! appsink {sink_props}"
                    )

            if has_v4l2convert and has_videoscale:
                configs.append(
                    f"{src} ! v4l2convert ! videoscale ! {scaled_caps} ! "
                    f"appsink {sink_props}"
                )

            if has_videoconvert and has_videoscale:
                configs.append(
                    f"{src} ! videoconvert ! videoscale ! {scaled_caps} ! "
                    f"appsink {sink_props}"
                )

        if has_glupload and has_glcolorconvert and has_gldownload:
            configs.append(
                f"{src} ! "
                f"glupload ! glcolorconvert ! gldownload ! "
                f"video/x-raw,format=RGB ! "
                f"appsink {sink_props}"
            )

        if has_glupload and has_glcolorscale and has_gldownload:
            configs.append(
                f"{src} ! "
                f"glupload ! glcolorscale ! gldownload ! "
                f"video/x-raw,format=RGB ! "
                f"appsink {sink_props}"
            )

        if has_v4l2convert:
            configs.append(
                f"{src} ! v4l2convert ! video/x-raw,format=RGB ! appsink {sink_props}"
            )

        if has_videoconvert:
            configs.append(
                f"{src} ! videoconvert ! video/x-raw,format=RGB ! appsink {sink_props}"
            )

        return configs

    @staticmethod
    def _config_key(pipeline_str: str) -> str:
        """Identify a pipeline config independent of node id and dimensions,
        so runtime failures can be remembered across restarts."""
        key = re.sub(r"path=\d+", "path=*", pipeline_str)
        key = re.sub(r"width=\d+", "width=*", key)
        key = re.sub(r"height=\d+", "height=*", key)
        return key

    def _start_pipeline(self) -> bool:
        if not self._portal_node_id:
            return False

        if self._pipeline:
            self._stop_gst_pipeline()

        configs = self._get_pipeline_configs(self._portal_node_id)
        if not configs:
            print("No suitable GStreamer pipeline configuration found")
            print("Need one of: glupload+glcolorconvert, v4l2convert, or videoconvert")
            self._log_pipeline_details()
            return False

        target_w, target_h = self._compute_scaled_dimensions()

        for i, pipeline_str in enumerate(configs):
            config_key = self._config_key(pipeline_str)
            if config_key in self._runtime_failed_configs:
                continue
            try:
                self._pipeline = Gst.parse_launch(pipeline_str)
                self._appsink = self._pipeline.get_by_name("sink")
                self._appsink.connect("new-sample", self._on_new_sample)

                bus = self._pipeline.get_bus()
                bus.add_signal_watch()
                bus.connect("message::error", self._on_pipeline_error)
                bus.connect("message::warning", self._on_pipeline_warning)
                bus.connect("message::element", self._on_pipeline_element_message)

                ret = self._pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    desc = (
                        pipeline_str.split(" ! ")[1]
                        if " ! " in pipeline_str
                        else "unknown"
                    )
                    print(f"Pipeline config {i + 1} failed (converter: {desc})")
                    self._pipeline.set_state(Gst.State.NULL)
                    self._pipeline = None
                    continue

                uses_scaled_caps = (
                    target_w is not None and f"width={target_w}" in pipeline_str
                )
                self._pipeline_scaled = uses_scaled_caps
                self._scaled_w = target_w
                self._scaled_h = target_h

                self._pipeline_running = True
                self._pipeline_error_logged = False
                self._active_config_key = config_key
                desc = (
                    pipeline_str.split(" ! ")[1] if " ! " in pipeline_str else "unknown"
                )
                scale_info = (
                    f", scaled to {target_w}x{target_h}" if uses_scaled_caps else ""
                )
                print(
                    f"GStreamer capture pipeline started (converter: {desc}{scale_info})"
                )
                return True

            except Exception as e:
                print(f"Pipeline config {i + 1} exception: {e}")
                if self._pipeline:
                    self._pipeline.set_state(Gst.State.NULL)
                    self._pipeline = None
                continue

        self._pipeline_scaled = False
        print("All pipeline configurations failed")
        self._log_pipeline_details()
        return False

    def _on_pipeline_error(self, bus, message):
        err, debug = message.parse_error()
        if not self._pipeline_error_logged:
            print(f"GStreamer pipeline error: {err.message}")
            print(f"GStreamer debug info: {debug}")
            self._pipeline_error_logged = True
        if self._active_config_key:
            self._runtime_failed_configs.add(self._active_config_key)
            print(
                "Marking pipeline config as failed; "
                "will fall back to next converter on restart"
            )
        self._stop_gst_pipeline()

    def _on_pipeline_warning(self, bus, message):
        warn, debug = message.parse_warning()
        print(f"GStreamer pipeline warning: {warn.message}")

    def _on_pipeline_element_message(self, bus, message):
        structure = message.get_structure()
        if structure and structure.get_name() == "missing-plugin":
            print(f"Missing GStreamer plugin: {structure.to_string()}")

    def _log_pipeline_details(self):
        if not self._pipeline:
            return
        try:
            state = self._pipeline.get_state(Gst.CLOCK_TIME_NONE)
            print(f"Pipeline state: {state}")
            print(f"PipeWire node ID: {self._portal_node_id}")
            plugins = {
                "pipewiresrc": Gst.ElementFactory.find("pipewiresrc") is not None,
                "videoconvert": Gst.ElementFactory.find("videoconvert") is not None,
                "videoscale": Gst.ElementFactory.find("videoscale") is not None,
                "v4l2convert": Gst.ElementFactory.find("v4l2convert") is not None,
                "glupload": Gst.ElementFactory.find("glupload") is not None,
                "glcolorconvert": Gst.ElementFactory.find("glcolorconvert") is not None,
                "gldownload": Gst.ElementFactory.find("gldownload") is not None,
                "glcolorscale": Gst.ElementFactory.find("glcolorscale") is not None,
            }
            print(f"GStreamer plugins: {plugins}")
        except Exception as e:
            print(f"Error logging pipeline details: {e}")

    @staticmethod
    def _extract_pixel_rows(
        data: bytes, width: int, height: int, bpp: int, stride: Optional[int]
    ) -> np.ndarray:
        """Return a (height, width*bpp) uint8 array, stripping row padding.

        GStreamer may pad each row to an alignment boundary (e.g. 4 bytes),
        so the buffer stride can exceed width*bpp. The real stride comes from
        GstVideoMeta when available, otherwise it is inferred from the buffer
        size.
        """
        row_bytes = width * bpp
        if not stride or stride < row_bytes:
            if len(data) == height * row_bytes:
                stride = row_bytes
            else:
                stride = len(data) // height if height else row_bytes
        if stride < row_bytes or len(data) < stride * (height - 1) + row_bytes:
            raise ValueError(
                f"Buffer too small: {len(data)} bytes for "
                f"{width}x{height} with bpp={bpp} (stride={stride})"
            )

        arr = np.frombuffer(data, dtype=np.uint8)
        if stride == row_bytes:
            return arr[: height * row_bytes].reshape(height, row_bytes)

        # Padded rows: build a strided view (handles a possibly unpadded
        # final row) and copy to detach from the mapped buffer.
        rows = np.lib.stride_tricks.as_strided(
            arr, shape=(height, row_bytes), strides=(stride, 1)
        )
        return rows.copy()

    def _on_new_sample(self, appsink) -> Gst.FlowReturn:
        try:
            sample = appsink.emit("pull-sample")
            if not sample:
                return Gst.FlowReturn.OK

            buffer = sample.get_buffer()
            caps = sample.get_caps()

            struct = caps.get_structure(0)
            width = struct.get_value("width")
            height = struct.get_value("height")
            fmt = struct.get_value("format") if struct.has_field("format") else None

            if not self._pipeline_scaled and (
                self._source_width != width or self._source_height != height
            ):
                self._source_width = width
                self._source_height = height
                if self.scale_factor < 1.0:
                    self._needs_pipeline_restart = True

            stride = None
            try:
                meta = GstVideo.buffer_get_video_meta(buffer)
                if meta and meta.n_planes >= 1:
                    stride = meta.stride[0]
            except Exception:
                stride = None

            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                print(f"Failed to map buffer (format={fmt}, {width}x{height})")
                print("This likely means DMA-BUF buffers are being received.")
                print("Ensure GStreamer GL plugins (gst-plugins-gl) are installed.")
                return Gst.FlowReturn.OK

            try:
                data = bytes(map_info.data)

                if fmt in ("RGBA", "RGBx", "BGRA", "BGRx"):
                    bpp = 4
                elif fmt in ("BGR15", "RGB15"):
                    bpp = 2
                else:
                    bpp = 3

                rows = self._extract_pixel_rows(data, width, height, bpp, stride)

                if fmt == "BGR":
                    frame = rows.reshape(height, width, 3)[:, :, ::-1].copy()
                elif fmt in ("RGBA", "RGBx"):
                    frame = rows.reshape(height, width, 4)
                elif fmt in ("BGRA", "BGRx"):
                    frame = rows.reshape(height, width, 4)[:, :, [2, 1, 0, 3]].copy()
                elif fmt in ("BGR15", "RGB15"):
                    arr = np.ascontiguousarray(rows).view(np.uint16).reshape(
                        (height, width)
                    )
                    r = ((arr >> 10) & 0x1F).astype(np.uint8) * 255 // 31
                    g = ((arr >> 5) & 0x1F).astype(np.uint8) * 255 // 31
                    b = (arr & 0x1F).astype(np.uint8) * 255 // 31
                    frame = np.stack([r, g, b], axis=2)
                else:
                    # RGB and unknown formats assumed 3 bytes per pixel
                    frame = rows.reshape(height, width, 3)

                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_frame_data = data

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
                    self._portal_session_handle,
                )
                session.Close()
                print("Portal session closed")
            except Exception as e:
                print(f"Error closing portal session (may already be closed): {e}")
        self._portal_session_handle = None
        self._portal_bus = None

    def stop_pipeline(self):
        self._stop_gst_pipeline()
        self._source_width = None
        self._source_height = None
        self._pipeline_scaled = False
        self._needs_pipeline_restart = False
        self._portal_node_id = None
        self._runtime_failed_configs.clear()
        print("GStreamer pipeline stopped")
        self._close_portal_session()

    def __del__(self):
        self.stop_pipeline()
