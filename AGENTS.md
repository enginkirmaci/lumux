# Lumux — Agent Development Guide

## Project Overview

Lumux is a **Philips Hue Sync application for Linux (Wayland)** that provides real-time ambient lighting synchronization. It captures screen content using the XDG Desktop Portal ScreenCast API (PipeWire) and streams color data to Philips Hue lights via the Hue Entertainment API (DTLS).

**Key Features:**
- Real-time screen capture using PipeWire/GStreamer portal pipeline
- DTLS-encrypted streaming to Hue Entertainment zones for low-latency updates
- GTK4 + libadwaita native GUI with Adwaita dark theme
- Ambilight-style edge zone layout (top/bottom/left/right zones)
- Video Mode (dynamic sync) and Reading Mode (static color)
- System tray integration with quick controls
- Black bar detection for letterbox/pillarbox content
- Multi-monitor support (via compositor portal support)
- Flatpak distribution support

## Technology Stack

**Core Technologies:**
- **Python 3.10+** — Application language
- **GTK 4.0 + libadwaita** — GUI framework
- **GStreamer + PipeWire** — Screen capture via XDG Desktop Portal
- **OpenSSL (system)** — DTLS-PSK connection for entertainment streaming
- **NumPy + Pillow** — Image processing
- **requests + urllib3** — REST API communication
- **pydbus** — D-Bus communication for portals
- **zeroconf** — mDNS bridge discovery

**Build System:**
- **setuptools** — Python packaging
- **Flatpak** — Primary distribution method
- **GNOME Platform 49** — Runtime base

## Project Structure

```
lumux/
├── main.py                      # Application entry point, LumuxApp class
├── pyproject.toml               # Python package configuration
├── requirements.txt             # Development dependencies
├── io.github.enginkirmaci.lumux.yml    # Flatpak manifest
├── python3-modules.json         # Flatpak Python dependencies
│
├── lumux/                       # Core application modules
│   ├── __init__.py
│   ├── app_context.py           # Application wiring, dependency injection
│   ├── bridge_client.py         # Unified Hue v2 REST API client
│   ├── hue_bridge.py            # High-level bridge interface, discovery
│   ├── capture.py               # Screen capture via PipeWire portal/GStreamer
│   ├── colors.py                # Color analysis, RGB→XY conversion, smoothing
│   ├── zones.py                 # Zone processing (ambilight edge zones)
│   ├── entertainment.py         # DTLS streaming to Hue Entertainment API
│   ├── sync.py                  # Main sync controller with threading
│   ├── mode_manager.py          # Video/Reading mode switching
│   ├── reading_mode.py          # Reading mode static lighting controller
│   ├── black_bar_detector.py    # Letterbox/pillarbox detection
│   └── utils/
│       ├── __init__.py
│       ├── logging.py           # timed_print utility
│       └── rgb_xy_converter.py  # RGB to CIE XY color conversion
│
├── gui/                         # GTK GUI components
│   ├── __init__.py
│   ├── main_window.py           # Main Adw.ApplicationWindow
│   ├── settings_dialog.py       # Adw.PreferencesDialog with settings pages
│   ├── bridge_wizard.py         # 3-step bridge setup wizard
│   ├── zone_preview_widget.py   # Real-time zone color visualization
│   └── tray_icon.py             # System tray integration
│
├── config/                      # Configuration management
│   ├── __init__.py
│   ├── settings_manager.py      # Singleton settings with dataclasses
│   └── zone_mapping.py          # Zone to light mapping management
│
├── utils/                       # Shared utilities
│   ├── __init__.py
│   └── rgb_xy_converter.py      # Color space conversion (sRGB→CIE XY)
│
└── data/                        # Application data files
    ├── default_settings.json    # Default configuration values
    ├── io.github.enginkirmaci.lumux.desktop    # Desktop entry
    └── io.github.enginkirmaci.lumux.metainfo.xml  # AppStream metadata
```

## Build and Run Commands

### Development Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Editable install
pip install -e .
```

### Run from Source

```bash
# Direct execution
python main.py

# Or if installed
lumux
```

### Build Flatpak

```bash
# Build the Flatpak package
flatpak-builder --force-clean build-dir io.github.enginkirmaci.lumux.yml

# Install locally for testing
flatpak-builder --user --install --force-clean build-dir io.github.enginkirmaci.lumux.yml

# Run the Flatpak build
flatpak run io.github.enginkirmaci.lumux
```

### Generate Flatpak Dependencies

```bash
# Install flatpak-builder-tools
# Then generate Python dependencies
flatpak-pip-generator --output python3-modules numpy Pillow requests pydbus zeroconf
```

## Code Style Guidelines

**General Style:**
- Follow PEP 8 conventions
- Use type hints where practical (typing module)
- Use dataclasses for data structures
- Prefer composition over inheritance
- Keep functions focused and under 50 lines where possible

**Naming Conventions:**
- `snake_case` for variables, functions, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Private methods prefixed with underscore: `_private_method()`
- Internal attributes prefixed with underscore: `self._internal_var`

**Imports:**
- Group imports: stdlib, third-party, local
- Use explicit imports (avoid `from module import *`)
- For GTK: always set version before importing
  ```python
  import gi
  gi.require_version("Gtk", "4.0")
  gi.require_version("Adw", "1")
  from gi.repository import Gtk, Adw
  ```

**Documentation:**
- Use docstrings for modules, classes, and public methods
- Google-style docstrings preferred
- Include type information in docstrings when helpful

## Architecture Patterns

**Dependency Injection via AppContext:**
The `AppContext` class (`lumux/app_context.py`) acts as the composition root:
```python
class AppContext:
    def __init__(self, settings: SettingsManager):
        self.bridge = HueBridge(...)
        self.capture = ScreenCapture(...)
        self.zone_processor = ZoneProcessor(...)
        self.sync_controller = SyncController(...)
        self.mode_manager = ModeManager(...)
```

**Settings Management:**
- Singleton `SettingsManager` pattern
- Dataclasses for typed settings groups
- Auto-save on changes via explicit `save()` calls
- Flatpak-aware config directory detection

**Threading Model:**
- Main thread: GUI operations only
- Sync loop: Background thread (`SyncController._sync_loop`)
- Bridge operations: May use threads for discovery/authentication
- Use `GLib.idle_add()` for thread-safe GUI updates

**Mode Management:**
- Modes are mutually exclusive: OFF, VIDEO, READING
- `ModeManager` handles transitions and cleanup
- Video mode uses DTLS streaming (continuous updates)
- Reading mode uses REST API (one-time static color)

## Key Implementation Details

**Screen Capture (lumux/capture.py):**
- Uses XDG Desktop Portal ScreenCast API (pydbus)
- GStreamer pipeline: `pipewiresrc → videoconvert → appsink`
- Continuous capture with `max-buffers=1, drop=true` for latest frame
- Scaling applied after capture via Pillow (BILINEAR for speed)
- Black bar detection processes before scaling for accuracy

**DTLS Streaming (lumux/entertainment.py):**
- Uses OpenSSL subprocess for DTLS-PSK connection
- Protocol: HueStream v2 over UDP port 2100
- PSK identity: hue-application-id from `/auth/v1` endpoint
- Color space: XY + Brightness (more accurate than RGB)
- Message format: Binary protocol with 16-bit color values

**Color Processing:**
1. Capture RGB image from screen
2. Extract zone colors (edge averages via NumPy)
3. Convert RGB → CIE XY with gamma correction
4. Apply gamut constraints per light capabilities
5. Apply exponential moving average smoothing
6. Map zones to entertainment channels by position
7. Send via DTLS with brightness scaling

**Zone Layout:**
- Ambilight style: edges only (top, bottom, left, right)
- Configurable rows (left/right zones) and columns (top/bottom zones)
- Zone IDs: `top_0`, `top_1`, ..., `left_0`, `left_1`, etc.
- Channel mapping based on 3D positions from entertainment config

## Testing Instructions

**Manual Testing Checklist:**
1. Bridge discovery (SSDP, mDNS, N-UPnP)
2. Authentication flow (press link button)
3. Entertainment zone loading
4. Video sync start/stop
5. Reading mode activation
6. Settings persistence
7. Flatpak sandbox behavior
8. System tray functionality

**Debug Output:**
The app uses `timed_print()` from `lumux/utils/logging.py` for timestamped logging:
```python
from lumux.utils.logging import timed_print
timed_print("Debug message")
# Output: [2024-01-15 10:30:45] Debug message
```

## Security Considerations

**Credentials:**
- Bridge IP, app_key, and client_key stored in `~/.config/lumux/settings.json`
- Client key is PSK for DTLS - treat as sensitive
- No encryption at rest for settings file

**Network:**
- DTLS-PSK encryption for entertainment streaming
- HTTPS for REST API (bridge uses self-signed cert, verification disabled)
- Local network only (Hue bridge is local device)

**Screen Capture:**
- Uses XDG Desktop Portal (user permission required)
- Portal dialog shows what's being captured
- No privileged access required
- User can revoke permission anytime

**Flatpak Sandboxing:**
- Network access required for bridge communication
- PipeWire access for screen capture
- Optional: filesystem access for autostart (user must grant)

## Configuration

**Settings File:** `~/.config/lumux/settings.json`

**Key Settings Groups:**
- `hue`: bridge_ip, app_key, client_key, entertainment_config_id
- `capture`: scale_factor (0.01-1.0)
- `zones`: rows, cols, show_preview
- `sync`: fps (1-60), transition_time_ms, brightness_scale, gamma, smoothing_factor
- `black_bar`: enabled, threshold, detection_rate, smooth_factor
- `reading_mode`: color_xy, brightness, auto_activate, light_ids
- `ui`: start_at_startup, minimize_to_tray_on_sync

**Validation:**
All settings are validated in `SettingsManager._validate_settings()` with clamping to safe ranges.

## Common Development Tasks

**Adding a New Setting:**
1. Add field to appropriate dataclass in `config/settings_manager.py`
2. Add default value to `data/default_settings.json`
3. Add UI control in `gui/settings_dialog.py`
4. Add save/load logic in `_load_settings()` and `save()`
5. Add validation in `_validate_settings()`

**Adding a New GUI Page:**
1. Create `Adw.PreferencesPage` in `gui/settings_dialog.py`
2. Add groups and rows using Adwaita widgets
3. Connect to settings and implement save logic

**Modifying Color Processing:**
- Color conversion: `utils/rgb_xy_converter.py`
- Analysis logic: `lumux/colors.py`
- Zone extraction: `lumux/zones.py`

**Adding Discovery Method:**
- Add method to `HueBridge.discover_bridges()` in `lumux/hue_bridge.py`
- Follow existing pattern with timeout and error handling

## Dependencies Notes

**System Requirements:**
- Linux with Wayland compositor
- xdg-desktop-portal with screen casting support
- GTK4 and libadwaita
- OpenSSL (for DTLS)

**Python Dependencies (see pyproject.toml):**
- numpy>=1.24.0
- Pillow>=10.0.0
- requests>=2.28.0
- urllib3>=1.26.0
- pydbus>=0.6.0
- zeroconf>=0.60.0

**Flatpak Runtime:**
- org.gnome.Platform//49
- org.gnome.Sdk//49

## License

MIT License — See LICENSE file
