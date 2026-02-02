# Lumux — Philips Hue Sync for Wayland

Real-time ambient lighting synchronization for Philips Hue lights on Linux (Wayland) using a GTK4/Adwaita interface.

Status: Active

Features
- Real-time screen capture and color synchronization
- Ambilight-style edge zone layout
- GTK4 + libadwaita native interface
- Configurable resolution scale and FPS for performance tuning
- Support for multiple Hue zones and lights
- RGB ↔ XY color conversion for Hue color accuracy
- Smooth color transitions with configurable smoothing
- Multi-monitor support (subject to compositor portal support)
- System tray integration when available

Requirements

System
- Linux with a Wayland compositor that supports screen-casting portals (xdg-desktop-portal)
- OpenSSL (system) required if using DTLS / entertainment streaming

Common packages (example on Fedora)
- gtk4, libadwaita, xdg-desktop-portal (install via your distro package manager)

Python
- Python 3.10+ recommended
- Install Python packages from requirements.txt (current list):
  - python-hue-v2>=0.1.0
  - numpy>=1.24.0
  - Pillow>=10.0.0
  - requests>=2.28.0
  - pydbus>=0.6.0

Install

From source
1. Clone the repository:
   git clone https://github.com/enginkirmaci/lumux.git
   cd lumux
2. Install dependencies:
   pip install -r requirements.txt
3. Run:
   python main.py
   or, if installed:
   lumux

Editable install
- pip install -e .

Usage

First time setup
1. Start the application:
   python main.py
   or
   lumux
2. Open Settings
3. Bridge Connection
   - Discover Bridges or enter IP manually
   - Click Authenticate and press the link button on your Hue bridge to obtain the app key
4. Zone Configuration
   - Configure ambilight zones for edge-based color capture
5. Sync Settings
   - Adjust transition time, brightness scale, smoothing, resolution scale and FPS
   - Save settings

Starting sync
1. Click Start Sync
2. Zone preview shows real-time screen colors
3. Hue lights will follow the captured colors
4. Click Stop Sync to stop

Configuration
- Settings are saved to ~/.config/lumux/settings.json
- Autostart can be enabled via settings (if supported by the system)

Performance tips
- Resolution scale: reduce (e.g. 0.125 or 0.0625) to lower CPU usage
- FPS: 15–30 is often sufficient
- Transition time and smoothing: increase for smoother output

Troubleshooting

Wayland screen capture issues
- Ensure xdg-desktop-portal is installed and properly configured on your distro
- Some compositors (or portal backends) may require additional user permissions or settings

Bridge connection issues
- Ensure your device is on the same local network as the Hue bridge
- Verify the bridge is reachable via the bridge web interface
- Temporarily test with firewall disabled if necessary

High CPU usage
- Lower FPS and resolution scale in settings

Contributing
Contributions welcome. Please open issues and pull requests. If you plan large changes, open an issue first to discuss.

License
MIT License

Acknowledgements / Notes
- Works with Hue v2 API library (python-hue-v2)
- Screen capture on Wayland depends on the compositor and the portal implementation
