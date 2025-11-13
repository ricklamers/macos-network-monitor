"""
NetMonitor - Real-time macOS network traffic monitor with GUI

A Python GUI application that wraps macOS's nettop command to provide
real-time per-process network traffic monitoring with visualization.
"""

from netmonitor.app import main, NetworkMonitor

__version__ = "0.1.0"
__all__ = ["main", "NetworkMonitor"]
