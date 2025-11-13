# Network Monitor

<img src="resources/network-monitor-icon.png" alt="Network Monitor Icon" width="64" height="64" />

Real-time macOS network traffic monitor with GUI showing per-process bandwidth usage.

<img width="1112" height="883" alt="Screenshot 2025-11-13 at 10 28 23 PM" src="https://github.com/user-attachments/assets/0e12e727-add9-4b51-bc21-fa437d786fa7" />

## Features

- **Real-time monitoring** - Updates every second via `nettop`
- **Per-process bandwidth** - See download/upload rates for each process
- **Live graphs** - 60-second bandwidth history  
- **Sortable columns** - Instant sorting by any column
- **Password caching** - Secure 24-hour storage in macOS Keychain
- **Native macOS app** - Launch from Spotlight/Launchpad

## Installation

### Build the App
```bash
./build_app.sh
cp -r "dist/Network Monitor.app" /Applications/
```

### Launch
- Spotlight: ⌘+Space → "Network Monitor"
- Or: `open "/Applications/Network Monitor.app"`

## How It Works

1. **Python.framework 3.10** - Uses system Python (has working Tk/Tcl)
2. **PTY wrapper** - Prevents `nettop` output buffering for real-time updates
3. **Keychain storage** - Securely stores sudo password (24h expiry)
4. **CSV parsing** - Parses `nettop -L 0 -J bytes_in,bytes_out` output

## Technical Details

**Why Python.framework 3.10 instead of uv Python?**
- uv Python (cpython-3.12.8-macos-aarch64-none) has Tk/Tcl version mismatches
- Python.framework comes with properly configured Tk/Tcl 8.6
- PYTHONPATH points to the source directory

**Why PTY?**
- `nettop` detects pipes and buffers output (~15 seconds)
- PTY tricks it into thinking it's a terminal → unbuffered output
- Result: True 1-second refresh rates

## Requirements

- macOS 10.15+
- Python.framework 3.10+ (for app bundle)
- `keyring` package (auto-installed)
- sudo access

## License

MIT

