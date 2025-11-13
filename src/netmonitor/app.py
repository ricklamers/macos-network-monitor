#!/usr/bin/env python3
"""
NetMonitor - Real-time macOS network traffic monitor with GUI
Wraps the nettop command and provides visualization
"""

import subprocess
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import threading
import time
import re
import os
import pty
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


class PasswordDialog(simpledialog.Dialog):
    """Custom password dialog"""
    def __init__(self, parent):
        self.password = None
        super().__init__(parent, title="Sudo Password Required")
    
    def body(self, frame):
        ttk.Label(frame, text="Network Monitor requires sudo access to run nettop.").pack(pady=5)
        ttk.Label(frame, text="Please enter your password:").pack(pady=5)
        
        self.password_entry = ttk.Entry(frame, show="•", width=30)
        self.password_entry.pack(pady=5)
        self.password_entry.focus()
        
        return self.password_entry
    
    def validate(self):
        self.password = self.password_entry.get()
        return True
    
    def apply(self):
        pass


class NetworkMonitor:
    def __init__(self, root, sudo_password=None):
        self.root = root
        self.root.title("Network Monitor")
        self.root.geometry("1400x800")
        self.sudo_password = sudo_password
        
        # Detect retina display scaling
        self.scale_factor = self.root.winfo_fpixels('1i') / 72.0
        if self.scale_factor > 1.5:  # Retina display
            self.dpi_scale = 2.0
        else:
            self.dpi_scale = 1.0
        
        # Data storage
        self.process_data = {}
        self.history = defaultdict(lambda: deque(maxlen=60))  # 60 seconds of history
        self.running = True
        self.sort_column = "download"
        self.sort_reverse = True
        
        # Modern color scheme
        self.colors = {
            'bg': '#1e1e1e',
            'fg': '#e0e0e0',
            'accent1': '#4A9EFF',  # Blue for download
            'accent2': '#FF6B9D',  # Pink for upload
            'grid': '#333333',
            'canvas_bg': '#2d2d2d',
            'header_bg': '#252525',
        }
        
        # Configure style
        self.setup_style()
        
        # Create UI
        self.setup_ui()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_network, daemon=True)
        self.monitor_thread.start()
        
        # Start UI update loop
        self.update_ui()
    
    def setup_style(self):
        """Configure modern dark theme styling"""
        style = ttk.Style()
        
        # Font configuration with fallbacks
        # Try SF Pro Display first, fall back to system fonts
        try:
            # Test if SF Pro Display is available
            test_font = ('SF Pro Display', 11)
            self.root.tk.call('font', 'actual', test_font)
            main_font = 'SF Pro Display'
            mono_font = 'SF Mono'
        except:
            # Fall back to cross-platform fonts
            main_font = 'Helvetica Neue' if self.root.tk.call('tk', 'windowingsystem') == 'aqua' else 'Arial'
            mono_font = 'Menlo' if self.root.tk.call('tk', 'windowingsystem') == 'aqua' else 'Courier New'
        
        # Configure dark theme
        self.root.configure(bg=self.colors['bg'])
        
        # Configure ttk styles
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'], 
                       font=(main_font, 11))
        style.configure('TButton', font=(main_font, 11))
        
        style.configure('Header.TLabel', 
                       font=(main_font, 20, 'bold'),
                       foreground=self.colors['fg'],
                       background=self.colors['bg'])
        
        style.configure('Status.TLabel',
                       font=(main_font, 11),
                       foreground=self.colors['accent1'],
                       background=self.colors['bg'])
        
        style.configure('Treeview',
                       background=self.colors['canvas_bg'],
                       foreground=self.colors['fg'],
                       fieldbackground=self.colors['canvas_bg'],
                       font=(mono_font, 11),
                       rowheight=28)
        
        style.configure('Treeview.Heading',
                       background=self.colors['header_bg'],
                       foreground=self.colors['fg'],
                       font=(main_font, 11, 'bold'))
        
        style.map('Treeview',
                 background=[('selected', self.colors['accent1'])],
                 foreground=[('selected', 'white')])
        
        style.map('Treeview.Heading',
                 background=[('active', self.colors['grid'])])
        
        # Configure LabelFrame with subtle border
        style.configure('Card.TLabelframe',
                       background=self.colors['bg'],
                       borderwidth=1,
                       relief='solid',
                       bordercolor=self.colors['grid'])
        
        # Configure the label part of LabelFrame
        # CRITICAL: Label widget needs tkinter background, not ttk background
        style.configure('Card.TLabelframe.Label',
                       font=(main_font, 13, 'bold'),
                       foreground=self.colors['fg'],
                       background=self.colors['bg'],
                       relief='flat',
                       borderwidth=0)
        
        # Additional attempt to force label background
        style.map('Card.TLabelframe.Label',
                 background=[(None, self.colors['bg'])])
        
        # Configure PanedWindow to hide the sash separator
        style.configure('TPanedwindow', background=self.colors['bg'])
        try:
            style.configure('Sash', background=self.colors['bg'], 
                           sashthickness=0)
        except:
            pass  # Some themes don't support Sash styling
        
        # Store fonts for later use
        self.main_font = main_font
        self.mono_font = mono_font
        
    def setup_ui(self):
        # Top frame for controls with padding
        control_frame = ttk.Frame(self.root, padding="15")
        control_frame.pack(fill=tk.X)
        
        ttk.Label(control_frame, text="Network Traffic Monitor", 
                 style='Header.TLabel').pack(side=tk.LEFT, padx=10)
        
        self.status_label = ttk.Label(control_frame, text="Status: Starting...", 
                                      style='Status.TLabel')
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        ttk.Button(control_frame, text="Clear History", 
                  command=self.clear_history).pack(side=tk.RIGHT, padx=5)
        
        # Main container (using Frame instead of PanedWindow to avoid sash separator)
        main_container = tk.Frame(self.root, bg=self.colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # Configure grid weights for 2/3 and 1/3 split
        main_container.grid_rowconfigure(0, weight=2)  # Process list gets 2/3
        main_container.grid_rowconfigure(1, weight=1)  # Graph gets 1/3
        main_container.grid_columnconfigure(0, weight=1)
        
        # Process list container
        list_container = tk.Frame(main_container, bg=self.colors['bg'])
        list_container.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        # Label for Processes section
        process_label = tk.Label(list_container, 
                                text="Processes",
                                font=(self.main_font, 13, 'bold'),
                                fg=self.colors['fg'],
                                bg=self.colors['bg'],
                                anchor='w')
        process_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Process list frame
        list_frame = tk.Frame(list_container, bg=self.colors['bg'])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("process", "pid", "download", "upload", "connections")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                yscrollcommand=tree_scroll.set, height=18)
        tree_scroll.config(command=self.tree.yview)
        
        # Configure columns with better widths
        column_config = {
            "process": ("Process", 280, tk.W),
            "pid": ("PID", 70, tk.CENTER),
            "download": ("Download", 140, tk.E),
            "upload": ("Upload", 140, tk.E),
            "connections": ("Conns", 80, tk.E)
        }
        
        for col, (heading, width, anchor) in column_config.items():
            self.tree.heading(col, text=heading, 
                            command=lambda c=col: self.sort_by_column(c))
            self.tree.column(col, width=width, anchor=anchor, minwidth=width)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Graph container
        graph_container = tk.Frame(main_container, bg=self.colors['bg'])
        graph_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # Label for Network Activity section
        activity_label = tk.Label(graph_container, 
                                  text="Network Activity (Last 60s)",
                                  font=(self.main_font, 13, 'bold'),
                                  fg=self.colors['fg'],
                                  bg=self.colors['bg'],
                                  anchor='w')
        activity_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Graph frame
        graph_frame = tk.Frame(graph_container, bg=self.colors['bg'])
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Canvas for graph with retina support
        self.canvas = tk.Canvas(graph_frame, bg=self.colors['canvas_bg'], 
                               highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Legend with modern styling (will be set after fonts are initialized)
        legend_frame = ttk.Frame(graph_frame)
        legend_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.download_legend = ttk.Label(legend_frame, text="● Download", 
                                        foreground=self.colors['accent1'])
        self.download_legend.pack(side=tk.LEFT, padx=15)
        
        self.upload_legend = ttk.Label(legend_frame, text="● Upload", 
                                      foreground=self.colors['accent2'])
        self.upload_legend.pack(side=tk.LEFT, padx=15)
        
        # Bottom status bar
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        
        self.total_label = ttk.Label(status_frame, 
                                     text="Total: ↓ 0 KB/s  ↑ 0 KB/s")
        self.total_label.pack(side=tk.LEFT)
        
        self.update_time_label = ttk.Label(status_frame, text="")
        self.update_time_label.pack(side=tk.RIGHT)
        
        # Update legend and status fonts after initialization
        self.root.after(100, self._update_custom_fonts)
    
    def _update_custom_fonts(self):
        """Update fonts for labels that need custom sizes"""
        self.download_legend.config(font=(self.main_font, 12, 'bold'))
        self.upload_legend.config(font=(self.main_font, 12, 'bold'))
        self.total_label.config(font=(self.main_font, 12, 'bold'))
        self.update_time_label.config(font=(self.mono_font, 10))
        
    def monitor_network(self):
        """Monitor network using nettop command"""
        try:
            # Run nettop with subprocess - simpler format
            if self.sudo_password:
                # First, authenticate sudo with the password
                auth_process = subprocess.Popen(
                    ["sudo", "-S", "-v"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                auth_process.stdin.write(self.sudo_password + "\n")
                auth_process.stdin.flush()
                auth_process.wait()
                
                if auth_process.returncode != 0:
                    raise Exception("Authentication failed")
                
                # Now run nettop without needing password (sudo session is cached)
                # Use -L 0 for infinite CSV samples, -s 1 for 1 second update interval
                # Remove -P flag to get connection-level data for counting connections
                # Use PTY to prevent output buffering (nettop buffers when piped)
                master, slave = pty.openpty()
                process = subprocess.Popen(
                    ["sudo", "nettop", "-x", "-L", "0", "-s", "1"],
                    stdout=slave,
                    stderr=slave,
                    text=True,
                    bufsize=1
                )
                os.close(slave)  # Close slave in parent process
                process_stdout = os.fdopen(master, 'r', buffering=1)
            else:
                # Prompt for password in terminal (fallback)
                # Use -L 0 for infinite CSV samples, -s 1 for 1 second update interval
                # Remove -P flag to get connection-level data for counting connections
                # Use PTY to prevent output buffering (nettop buffers when piped)
                master, slave = pty.openpty()
                process = subprocess.Popen(
                    ["sudo", "nettop", "-x", "-L", "0", "-s", "1"],
                    stdout=slave,
                    stderr=slave,
                    text=True,
                    bufsize=1
                )
                os.close(slave)  # Close slave in parent process
                process_stdout = os.fdopen(master, 'r', buffering=1)
            
            previous_data = {}
            
            while self.running:
                # Read one complete snapshot (until we hit the header again or EOF)
                current_snapshot = {}  # Process summaries: proc_id -> data
                connection_counts = defaultdict(int)  # Process connection counts
                current_process = None  # Track current process for connection counting
                
                while self.running:
                    line = process_stdout.readline()
                    
                    if not line:
                        self.running = False
                        break
                    
                    line = line.strip()
                    
                    # Check if this is a header line (start of new iteration)
                    # Header format: time,,interface,state,bytes_in,bytes_out,...
                    if line.startswith('time,') or line.startswith(',interface,state'):
                        if current_snapshot:  # If we already have data, this is the start of next iteration
                            break
                        else:  # First header, skip it
                            continue
                    
                    if not line:
                        continue
                    
                    # Parse the line
                    parsed = self.parse_nettop_line(line)
                    if parsed:
                        if parsed.get('is_connection'):
                            # This is a connection entry, count it for the current process
                            if current_process:
                                connection_counts[current_process] += 1
                        else:
                            # This is a process summary
                            proc_id = f"{parsed['name']}_{parsed['pid']}"
                            current_snapshot[proc_id] = parsed
                            current_process = proc_id  # Update current process
                    else:
                        # Check if this is a connection line that we couldn't parse
                        # (connections appear after process summaries)
                        parts = line.split(',')
                        if len(parts) > 1:
                            identifier = parts[1]  # Column 1 is the identifier (column 0 is time)
                            # If it looks like a connection (contains <-> or starts with tcp/udp)
                            if identifier and ('<->' in identifier or identifier.startswith(('tcp', 'udp', 'tcp4', 'tcp6', 'udp4', 'udp6'))):
                                if current_process:
                                    connection_counts[current_process] += 1
                
                if not self.running:
                    break
                
                # Calculate rates by comparing with previous snapshot
                if previous_data:
                    for proc_id, curr_data in current_snapshot.items():
                        if proc_id in previous_data:
                            prev = previous_data[proc_id]
                            dt = 1.0  # nettop updates every 1 second
                            
                            download_rate = max(0, curr_data['bytes_in'] - prev['bytes_in']) / dt
                            upload_rate = max(0, curr_data['bytes_out'] - prev['bytes_out']) / dt
                            
                            self.process_data[proc_id] = {
                                'name': curr_data['name'],
                                'pid': curr_data['pid'],
                                'download_rate': download_rate,
                                'upload_rate': upload_rate,
                                'connections': connection_counts.get(proc_id, 0)
                            }
                    
                    # Update totals for graph
                    total_download = sum(d.get('download_rate', 0) for d in self.process_data.values())
                    total_upload = sum(d.get('upload_rate', 0) for d in self.process_data.values())
                    
                    self.history['total_download'].append(total_download)
                    self.history['total_upload'].append(total_upload)
                    self.history['timestamp'].append(time.time())
                
                # Save current snapshot for next iteration
                previous_data = current_snapshot
            
            process.terminate()
                    
        except Exception as e:
            try:
                self.status_label.config(text=f"Error: {e}", foreground="red")
            except:
                pass
    
    def parse_nettop_line(self, line):
        """Parse a line from nettop output (CSV format)
        Format: time,identifier,interface,state,bytes_in,bytes_out,...
        For process summaries: time,processname.pid,,,bytes_in,bytes_out,...
        For connections: time,connection_string,interface,state,bytes_in,bytes_out,...
        """
        try:
            parts = line.strip(',').split(',')
            
            if len(parts) < 6:
                return None
            
            # Column 0 is time, column 1 is the identifier
            identifier = parts[1] if len(parts) > 1 else ''
            
            if not identifier:
                return None
            
            # Check if this is a connection entry (contains <-> or connection pattern)
            is_connection = '<->' in identifier or identifier.startswith(('tcp', 'udp', 'tcp4', 'tcp6', 'udp4', 'udp6'))
            
            if is_connection:
                # Connection entry format: time,connection_string,interface,state,bytes_in,bytes_out,...
                # bytes_in is at index 4, bytes_out is at index 5
                try:
                    bytes_in = int(parts[4]) if len(parts) > 4 else 0
                    bytes_out = int(parts[5]) if len(parts) > 5 else 0
                except (ValueError, IndexError):
                    return None
                
                # Return connection info for counting (process association handled in caller)
                return {
                    'is_connection': True,
                    'bytes_in': bytes_in,
                    'bytes_out': bytes_out
                }
            else:
                # Process summary format: time,processname.pid,,,bytes_in,bytes_out,...
                # Extract process name and PID
                match = re.match(r'(.+?)\.(\d+)$', identifier)
                if not match:
                    return None
                
                name = match.group(1)
                pid = match.group(2)
                
                # Bytes are in columns 4 and 5 (after time, process, and two empty columns)
                try:
                    bytes_in = int(parts[4]) if len(parts) > 4 else 0
                    bytes_out = int(parts[5]) if len(parts) > 5 else 0
                except (ValueError, IndexError):
                    return None
                
                return {
                    'name': name,
                    'pid': pid,
                    'bytes_in': bytes_in,
                    'bytes_out': bytes_out,
                    'is_connection': False
                }
        except Exception as e:
            return None
    
    def update_ui(self):
        """Update the UI with current data"""
        if not self.running:
            return
        
        # Save currently selected items by process_pid
        selected_items = self.tree.selection()
        selected_processes = set()
        for item in selected_items:
            values = self.tree.item(item)['values']
            if values:
                # Store process_pid combination
                selected_processes.add(f"{values[0]}_{values[1]}")
        
        # Update process list
        self.tree.delete(*self.tree.get_children())
        
        # Sort data
        sorted_data = sorted(
            self.process_data.items(),
            key=lambda x: x[1].get(self.sort_column.replace('download', 'download_rate')
                                           .replace('upload', 'upload_rate'), 0),
            reverse=self.sort_reverse
        )
        
        total_down = 0
        total_up = 0
        
        for proc_id, data in sorted_data:
            download_rate = data['download_rate']
            upload_rate = data['upload_rate']
            
            # Only show processes with activity
            if download_rate < 100 and upload_rate < 100:
                continue
            
            total_down += download_rate
            total_up += upload_rate
            
            item_id = self.tree.insert("", tk.END, values=(
                data['name'],
                data['pid'],
                self.format_bytes(download_rate) + "/s",
                self.format_bytes(upload_rate) + "/s",
                data.get('connections', 0)
            ))
            
            # Restore selection if this process was previously selected
            process_key = f"{data['name']}_{data['pid']}"
            if process_key in selected_processes:
                self.tree.selection_add(item_id)
        
        # Update totals
        self.total_label.config(
            text=f"Total: ↓ {self.format_bytes(total_down)}/s  ↑ {self.format_bytes(total_up)}/s"
        )
        
        # Update status
        self.status_label.config(text="Status: Running", foreground=self.colors['accent1'])
        self.update_time_label.config(text=f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        # Draw graph
        self.draw_graph()
        
        # Schedule next update (every 1000ms to match nettop interval)
        self.root.after(1000, self.update_ui)
    
    def draw_graph(self):
        """Draw network activity graph with retina display support"""
        self.canvas.delete("all")
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width < 100 or height < 50:
            return
        
        download_history = list(self.history['total_download'])
        upload_history = list(self.history['total_upload'])
        
        if not download_history:
            return
        
        # Calculate max value for scaling with some headroom
        all_values = download_history + upload_history
        max_value = max(all_values) if all_values else 1
        if max_value == 0:
            max_value = 1
        max_value = max_value * 1.1  # Add 10% headroom
        
        # Graph dimensions
        margin_left = 80
        margin_right = 20
        margin_top = 20
        margin_bottom = 30
        
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        # Draw grid lines and labels
        num_grid_lines = 5
        for i in range(num_grid_lines):
            y = margin_top + (i * graph_height / (num_grid_lines - 1))
            
            # Grid line
            self.canvas.create_line(
                margin_left, y, width - margin_right, y,
                fill=self.colors['grid'], width=1 * self.dpi_scale, dash=(4, 4)
            )
            
            # Y-axis label
            value = max_value * (1 - i / (num_grid_lines - 1))
            self.canvas.create_text(
                margin_left - 10, y,
                text=self.format_bytes(value) + "/s",
                anchor=tk.E,
                fill=self.colors['fg'],
                font=(self.mono_font, 10)
            )
        
        # Draw download line (no area fill)
        if len(download_history) > 1:
            line_points = []
            
            for i, value in enumerate(download_history):
                x = margin_left + (i * graph_width / max(len(download_history) - 1, 1))
                y = margin_top + graph_height - (value / max_value * graph_height)
                line_points.extend([x, y])
            
            # Draw the line
            if len(line_points) >= 4:
                self.canvas.create_line(
                    line_points,
                    fill=self.colors['accent1'],
                    width=3 * self.dpi_scale,
                    smooth=True,
                    splinesteps=12
                )
        
        # Draw upload line (no area fill)
        if len(upload_history) > 1:
            line_points = []
            
            for i, value in enumerate(upload_history):
                x = margin_left + (i * graph_width / max(len(upload_history) - 1, 1))
                y = margin_top + graph_height - (value / max_value * graph_height)
                line_points.extend([x, y])
            
            # Draw the line
            if len(line_points) >= 4:
                self.canvas.create_line(
                    line_points,
                    fill=self.colors['accent2'],
                    width=3 * self.dpi_scale,
                    smooth=True,
                    splinesteps=12
                )
        
        # Draw axes with proper scaling
        # X-axis
        self.canvas.create_line(
            margin_left, height - margin_bottom,
            width - margin_right, height - margin_bottom,
            fill=self.colors['fg'],
            width=2 * self.dpi_scale
        )
        # Y-axis
        self.canvas.create_line(
            margin_left, margin_top,
            margin_left, height - margin_bottom,
            fill=self.colors['fg'],
            width=2 * self.dpi_scale
        )
        
        # X-axis label
        self.canvas.create_text(
            width / 2, height - 5,
            text="Time (last 60 seconds)",
            fill=self.colors['fg'],
            font=(self.main_font, 10)
        )
    
    def format_bytes(self, bytes_val):
        """Format bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} TB"
    
    def sort_by_column(self, col):
        """Sort treeview by column"""
        if col == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = True
        
        # Trigger immediate UI update for instant feedback
        self.update_ui()
    
    def clear_history(self):
        """Clear graph history"""
        self.history.clear()
    
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        self.root.destroy()


def get_stored_password():
    """Retrieve stored password from keychain if valid (< 24 hours old)"""
    if not KEYRING_AVAILABLE:
        return None
    
    try:
        # Get password and timestamp from keychain
        stored_data = keyring.get_password("netmonitor", "sudo_password")
        if not stored_data:
            return None
        
        # Parse stored data (format: "timestamp|password")
        parts = stored_data.split("|", 1)
        if len(parts) != 2:
            return None
        
        timestamp_str, password = parts
        stored_time = datetime.fromisoformat(timestamp_str)
        
        # Check if password is less than 24 hours old
        if datetime.now() - stored_time < timedelta(hours=24):
            return password
        else:
            # Password expired, delete it
            keyring.delete_password("netmonitor", "sudo_password")
            return None
    except Exception:
        return None


def store_password(password):
    """Store password in keychain with current timestamp"""
    if not KEYRING_AVAILABLE:
        return
    
    try:
        # Store password with timestamp (format: "timestamp|password")
        timestamp = datetime.now().isoformat()
        stored_data = f"{timestamp}|{password}"
        keyring.set_password("netmonitor", "sudo_password", stored_data)
    except Exception:
        pass


def test_sudo_password(password):
    """Test if a sudo password is valid"""
    test_process = subprocess.Popen(
        ["sudo", "-S", "-v"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    test_process.stdin.write(password + "\n")
    test_process.stdin.flush()
    test_process.wait()
    return test_process.returncode == 0


def main():
    """Main entry point for the application"""
    # Create root window (hidden initially)
    root = tk.Tk()
    root.withdraw()
    
    # Bring app to foreground on macOS
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    
    sudo_password = None
    
    # Try to get stored password first
    stored_password = get_stored_password()
    if stored_password and test_sudo_password(stored_password):
        sudo_password = stored_password
    else:
        # Ask for password
        dialog = PasswordDialog(root)
        sudo_password = dialog.password
        
        if not sudo_password:
            messagebox.showerror("Error", "Password is required to run Network Monitor")
            root.destroy()
            return
        
        # Test the password
        if not test_sudo_password(sudo_password):
            messagebox.showerror("Error", "Invalid password. Please try again.")
            root.destroy()
            return
        
        # Store the valid password
        store_password(sudo_password)
    
    # Show main window
    root.deiconify()
    
    # Create and run the app
    app = NetworkMonitor(root, sudo_password)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

