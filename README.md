# Philips Hue Sync for Wayland

Real-time ambient lighting synchronization for Philips Hue lights on Fedora Linux (Wayland).

## Features

- Real-time screen capture and color synchronization
- Multiple zone layouts (Ambilight, Grid, Custom)
- GTK4 native interface
- Optimized performance with configurable resolution and FPS
- Support for multiple Hue zones and lights
- RGB to XY color space conversion for accurate colors
- Smooth color transitions with configurable smoothing
- Multi-monitor support

## Requirements

### System Dependencies (Fedora)

```bash
sudo dnf install gtk4-devel gobject-introspection-devel python3-devel
sudo dnf install libadwaita-devel
sudo dnf install grim  # Optional fallback screenshot tool
```

### Python Dependencies

Install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

Or install with setup.py:

```bash
pip install -e .
```

## Installation

### From Source

```bash
git clone <repository-url>
cd lumux
pip install -r requirements.txt
python main.py
```

### With setup.py

```bash
pip install -e .
lumux
```

## Usage

### First Time Setup

1. Run the application:
   ```bash
   python main.py
   ```
   or
   ```bash
   lumux
   ```

2. Click **Settings** button

3. **Bridge Connection** tab:
   - Click **Discover Bridges** to find your Hue bridge on the network
   - Or manually enter the bridge IP address
   - Click **Authenticate** and press the link button on your bridge
   - The app key will be automatically populated

4. **Zone Configuration** tab:
   - Choose your zone layout (Ambilight, Grid, or Custom)
   - Set grid dimensions if using grid layout

5. **Sync Settings** tab:
   - Adjust transition time, brightness scale, and smoothing factor
   - Click **Save**

### Starting Sync

1. Click **Start Sync** button
2. The zone preview will show real-time screen colors
3. Your Hue lights will sync with screen colors
4. Click **Stop Sync** to stop

### Configuration

Settings are automatically saved to `~/.config/lumux/settings.json`

Zone mappings are saved to `~/.config/lumux/zones.json`

## Zone Layouts

### Ambilight
Captures colors from screen edges (top, bottom, left, right). Best for lights placed around your monitor.

### Grid
Divides screen into a configurable grid. Each grid cell maps to a zone. Good for setups with many lights.

### Custom
For advanced zone configuration (coming soon).

## Performance Tips

- **Resolution Scale**: Lower scale factor (0.125 = 1/8 resolution) improves performance
- **FPS**: 15-30 FPS is usually sufficient for smooth syncing
- **Transition Time**: Higher values (100-300ms) provide smoother transitions
- **Smoothing Factor**: 0.3-0.5 provides balanced color transitions

## Troubleshooting

### Wayland Screen Capture Issues

If screen capture doesn't work on Wayland:

1. Check that you have proper permissions:
   ```bash
   # Ensure xdg-desktop- portal is installed
   sudo dnf install xdg-desktop-portal
   ```

2. Some Wayland compositors may require additional configuration

### Bridge Connection Issues

1. Ensure your device is on the same network as the Hue bridge
2. Try disabling firewall temporarily to test
3. Check that the Hue bridge is accessible via web interface

### High CPU Usage

- Reduce FPS in settings (try 10-15 FPS)
- Lower resolution scale (try 0.0625 = 1/16 resolution)

## Development

### Project Structure

```
lumux/
├── main.py                 # Application entry point
├── hue_sync/               # Core sync modules
│   ├── bridge.py           # Hue bridge connection
│   ├── capture.py          # Screen capture
│   ├── zones.py            # Zone processing
│   ├── colors.py           # Color analysis
│   └── sync.py            # Main sync controller
├── gui/                   # GTK4 interface
│   ├── main_window.py      # Main window
│   ├── settings_dialog.py  # Settings dialog
│   └── zone_preview_widget.py  # Zone visualization
├── config/                # Configuration
│   ├── settings_manager.py  # Settings management
│   └── zone_mapping.py    # Zone to light mapping
├── utils/                 # Utilities
│   └── rgb_xy_converter.py # Color conversion
├── data/                  # Default data files
├── requirements.txt
├── setup.py
└── README.md
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.
