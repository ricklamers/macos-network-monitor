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
import colorsys
import math
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
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Set window size: 1000px wide, 70% of screen height
        window_width = 1000
        window_height = int(screen_height * 0.7)
        
        # Center the window both horizontally and vertically
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        
        # Set geometry: width x height + x + y
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        # Set minimum window size
        self.root.minsize(800, 600)
        self.sudo_password = sudo_password
        
        # Detect retina display scaling
        self.scale_factor = self.root.winfo_fpixels('1i') / 72.0
        if self.scale_factor > 1.5:  # Retina display
            self.dpi_scale = 2.0
        else:
            self.dpi_scale = 1.0
        
        # Data storage
        self.process_data = {}
        self.history = defaultdict(lambda: {'download': deque(maxlen=60), 'upload': deque(maxlen=60)})  # Per-process history
        self.history['timestamp'] = deque(maxlen=60)  # Shared timestamps
        self.running = True
        self.sort_column = "download"
        self.sort_reverse = True
        
        # Hover tracking
        self.hover_tooltip = None
        self.hover_data_points = []  # Store line segments for hover detection
        self.hover_highlights = []  # Store highlight markers (circles, vertical line)
        self.is_paused = False  # Track if graph updates are paused
        # Log scale parameters for hover detection (updated in draw_graph)
        self.log_min = 0.0
        self.log_max = 1.0
        self.log_range = 1.0
        self.min_value = 1.0
        self.max_value = 1.0
        self.graph_height = 0
        self.margin_top = 20
        self.margin_bottom = 30
        
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
        # Pack this first to ensure it's on top and clickable
        self.control_frame = ttk.Frame(self.root, padding="15")
        self.control_frame.pack(fill=tk.X, side=tk.TOP, before=None)
        
        ttk.Label(self.control_frame, text="Network Traffic Monitor", 
                 style='Header.TLabel').pack(side=tk.LEFT, padx=10)
        
        self.status_label = ttk.Label(self.control_frame, text="Status: Starting...", 
                                      style='Status.TLabel')
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Pause/Play button
        self.pause_button = ttk.Button(self.control_frame, text="⏸ Pause", 
                                      command=self.toggle_pause)
        self.pause_button.pack(side=tk.RIGHT, padx=5)
        
        # Clear History button
        ttk.Button(self.control_frame, text="Clear History", 
                  command=self.clear_history).pack(side=tk.RIGHT, padx=5)
        
        # Create scrollable frame for main content
        # Use Canvas with scrollbars for scrollable content
        # Ensure it doesn't overlap control_frame by packing after it
        canvas_frame = tk.Frame(self.root, bg=self.colors['bg'])
        canvas_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, after=self.control_frame)
        
        # Create canvas and scrollbars
        canvas = tk.Canvas(canvas_frame, bg=self.colors['bg'], highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack scrollbars and canvas
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Main container inside the canvas
        main_container = tk.Frame(canvas, bg=self.colors['bg'])
        # Start canvas window at y=0, but ensure it doesn't overlap control_frame
        # The control_frame is packed above, so canvas content starts below it
        canvas_window = canvas.create_window(15, 0, anchor=tk.NW, window=main_container)
        
        # Update scroll region when main_container size changes
        def update_scroll_region(event=None):
            # Update canvas window width to match canvas width (minus padding)
            canvas_width = canvas.winfo_width()
            if canvas_width > 1:  # Canvas has been rendered
                canvas.itemconfig(canvas_window, width=canvas_width - 30)  # 15px padding on each side
            
            # Update scroll region to include all content
            bbox = canvas.bbox("all")
            if bbox:
                # Only set scroll region if content is larger than viewport
                canvas_height = canvas.winfo_height()
                content_height = bbox[3] - bbox[1]
                
                if content_height > canvas_height:
                    # Content exceeds viewport - enable scrolling
                    canvas.configure(scrollregion=bbox)
                else:
                    # Content fits in viewport - disable scrolling by setting scrollregion to viewport size
                    canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
                    # Reset scroll position to top
                    canvas.yview_moveto(0)
        
        main_container.bind('<Configure>', update_scroll_region)
        canvas.bind('<Configure>', update_scroll_region)
        
        # Also update scroll region periodically to catch dynamic content changes
        def periodic_scroll_update():
            update_scroll_region()
            self.root.after(100, periodic_scroll_update)
        
        self.root.after(200, periodic_scroll_update)
        
        # Add mouse wheel scrolling - bind to canvas and main_container
        def on_mousewheel(event):
            # Check if scrolling is actually needed
            bbox = canvas.bbox("all")
            if not bbox:
                return
            
            canvas_height = canvas.winfo_height()
            content_height = bbox[3] - bbox[1]
            
            # Only scroll if content exceeds viewport
            if content_height <= canvas_height:
                return
            
            # Handle different platforms
            if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
                canvas.yview_scroll(1, "units")
            elif hasattr(event, 'delta'):
                # Windows/Mac with delta
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Bind mouse wheel to canvas (works on Windows, Mac, and Linux)
        def bind_mousewheel(widget):
            widget.bind("<MouseWheel>", on_mousewheel, add=True)
            widget.bind("<Button-4>", on_mousewheel, add=True)
            widget.bind("<Button-5>", on_mousewheel, add=True)
        
        # Bind to canvas and main_container
        bind_mousewheel(canvas)
        bind_mousewheel(main_container)
        
        # Also bind to all children of main_container
        def bind_children(parent):
            for child in parent.winfo_children():
                bind_mousewheel(child)
                if child.winfo_children():
                    bind_children(child)
        
        # Bind after a short delay to ensure all widgets are created
        self.root.after(100, lambda: bind_children(main_container))
        
        # Store canvas reference for scroll updates
        self.scroll_canvas = canvas
        self.scroll_main_container = main_container
        
        # Configure initial grid weights - will be recalculated dynamically
        # Start with graph getting more space to approximate 50% of total UI
        # Set minimum sizes to prevent clipping
        # Process list should be much smaller - set a fixed maximum height
        main_container.grid_rowconfigure(0, weight=1, minsize=150)  # Process list - smaller minimum
        main_container.grid_rowconfigure(1, weight=25, minsize=270)  # Graph gets more space initially (legend removed)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Process list container - set maximum height so it doesn't grow too large
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
        
        # Process list frame - make scrollable (Treeview has its own scrollbar)
        list_frame = tk.Frame(list_container, bg=self.colors['bg'])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create treeview with scrollbar - reduce height significantly
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("process", "pid", "download", "upload", "connections")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                yscrollcommand=tree_scroll.set, height=6)  # Reduced from 18 to 6 rows
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
        
        # Graph container - will be sized to exactly 50% of total window height
        self.graph_container = tk.Frame(main_container, bg=self.colors['bg'])
        self.graph_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # Store reference to main_container for height calculations
        self.main_container = main_container
        
        # Label for Network Activity section
        activity_label = tk.Label(self.graph_container, 
                                  text="Network Activity (Last 60s)",
                                  font=(self.main_font, 13, 'bold'),
                                  fg=self.colors['fg'],
                                  bg=self.colors['bg'],
                                  anchor='w')
        activity_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Graph frame
        graph_frame = tk.Frame(self.graph_container, bg=self.colors['bg'])
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Canvas for graph with retina support
        # Set minimum height to prevent clipping
        self.canvas = tk.Canvas(graph_frame, bg=self.colors['canvas_bg'], 
                               highlightthickness=0, height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Bind mouse events for hover
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        
        # Don't lift widgets - packing order already ensures proper z-ordering
        # Repeated lifting can interfere with button click event handling
        # The control_frame is already packed first, so it's on top by default
        
        # Bottom status bar
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        
        self.total_label = ttk.Label(self.status_frame, 
                                     text="Total: ↓ 0 KB/s  ↑ 0 KB/s")
        self.total_label.pack(side=tk.LEFT)
        
        self.update_time_label = ttk.Label(self.status_frame, text="")
        self.update_time_label.pack(side=tk.RIGHT)
        
        # Update legend and status fonts after initialization
        self.root.after(100, self._update_custom_fonts)
        
        # Set up resize handler to maintain graph at 50% of total window height
        self.root.bind('<Configure>', self.on_window_resize)
        # Call multiple times to ensure it runs after window is fully rendered
        self.root.after(100, self.update_graph_height)
        self.root.after(300, self.update_graph_height)
        self.root.after(500, self.update_graph_height)
    
    def _update_custom_fonts(self):
        """Update fonts for labels that need custom sizes"""
        self.total_label.config(font=(self.main_font, 12, 'bold'))
        self.update_time_label.config(font=(self.mono_font, 10))
    
    def toggle_pause(self):
        """Toggle pause/play state"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.config(text="▶ Play")
        else:
            self.pause_button.config(text="⏸ Pause")
            # Resume updates immediately
            self.update_ui()
    
    def on_window_resize(self, event):
        """Handle window resize to maintain graph at 50% height"""
        if event.widget == self.root:
            self.root.after_idle(self.update_graph_height)
    
    def update_graph_height(self):
        """Set graph container so canvas takes exactly 50% of total window height"""
        try:
            # Wait for window to be fully rendered
            self.root.update_idletasks()
            
            # Get total window height
            total_height = self.root.winfo_height()
            if total_height < 100:  # Window not ready yet
                return
            
            # Get header and status bar heights
            header_height = self.control_frame.winfo_height() if hasattr(self, 'control_frame') else 60
            status_height = self.status_frame.winfo_height() if hasattr(self, 'status_frame') else 40
            
            # Calculate available height for main container
            available_height = total_height - header_height - status_height
            if available_height <= 0:
                return
            
            # Minimum heights to prevent clipping (in pixels)
            min_process_height = 150  # Reduced minimum height for process list (it will scroll if needed)
            min_graph_container_height = 270  # Minimum height for graph container (label + canvas, legend removed)
            
            # Graph container overhead: label + padding (legend removed)
            graph_label_height = 35  # "Network Activity (Last 60s)" label
            graph_padding = 25  # Padding around graph_frame (top + bottom)
            graph_overhead = graph_label_height + graph_padding
            min_canvas_height = min_graph_container_height - graph_overhead  # ~210px minimum canvas
            
            # Set canvas minimum height
            self.canvas.config(height=max(min_canvas_height, 250))
            
            # Target: canvas should be 50% of total window height
            target_canvas_height = total_height / 2
            
            # So graph_container needs to be: target_canvas_height + overhead
            target_graph_container_height = target_canvas_height + graph_overhead
            
            # Ensure we never go below minimums
            target_graph_container_height = max(target_graph_container_height, min_graph_container_height)
            
            # Check if we have enough space for minimums
            if available_height < (min_process_height + min_graph_container_height):
                # Not enough space - enforce minimums and let process list scroll
                # This should be prevented by minsize, but handle it anyway
                process_height = min_process_height
                graph_height = available_height - process_height
                graph_height = max(graph_height, min_graph_container_height)
            else:
                # Enough space - use target calculation
                graph_height = target_graph_container_height
            
            # Calculate what fraction of available_height the graph should take
            graph_fraction = graph_height / available_height
            graph_fraction = max(0.4, min(0.95, graph_fraction))
            
            # Calculate weights: process_weight : graph_weight = (1-F) : F
            process_weight = 10
            if graph_fraction < 1.0:
                graph_weight = int(10 * graph_fraction / (1 - graph_fraction))
                graph_weight = max(15, graph_weight)  # Ensure graph gets substantial space
            else:
                graph_weight = 100
            
            # Update grid weights
            # Process list gets minimal weight - it should stay compact and scroll
            self.main_container.grid_rowconfigure(0, weight=1, minsize=min_process_height)
            self.main_container.grid_rowconfigure(1, weight=graph_weight, minsize=min_graph_container_height)
            
        except Exception as e:
            # If calculation fails, use safe default that prevents clipping
            try:
                self.main_container.grid_rowconfigure(0, weight=1, minsize=150)
                self.main_container.grid_rowconfigure(1, weight=20, minsize=270)
            except:
                pass
        
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
                    
                    # Update per-process history for graph
                    for proc_id, data in self.process_data.items():
                        if proc_id not in self.history:
                            self.history[proc_id] = {'download': deque(maxlen=60), 'upload': deque(maxlen=60)}
                        self.history[proc_id]['download'].append(data.get('download_rate', 0))
                        self.history[proc_id]['upload'].append(data.get('upload_rate', 0))
                    
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
        # Only update if not paused
        if not self.is_paused:
            self.root.after(1000, self.update_ui)
    
    def draw_graph(self):
        """Draw network activity graph with per-process lines and hover support"""
        self.canvas.delete("all")
        self.hover_data_points = []  # Reset hover data points
        self.hover_highlights = []  # Reset highlights
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width < 100 or height < 50:
            return
        
        # Collect all process histories
        process_histories = {}
        for proc_id in self.history.keys():
            if proc_id == 'timestamp':
                continue
            if proc_id in self.process_data:
                process_histories[proc_id] = {
                    'download': list(self.history[proc_id]['download']),
                    'upload': list(self.history[proc_id]['upload']),
                    'name': self.process_data[proc_id]['name']
                }
        
        if not process_histories:
            return
        
        # Calculate max value for scaling with some headroom
        all_values = []
        for proc_data in process_histories.values():
            all_values.extend(proc_data['download'])
            all_values.extend(proc_data['upload'])
        
        max_value = max(all_values) if all_values else 1
        if max_value == 0:
            max_value = 1
        max_value = max_value * 1.1  # Add 10% headroom
        
        # For log scale, we need a minimum value > 0
        # Use 1 byte/s as minimum to avoid log(0)
        min_value = 1.0
        
        # Graph dimensions
        margin_left = 80
        margin_right = 20
        margin_top = 20
        margin_bottom = 30
        
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        # Calculate log scale range
        log_min = math.log10(min_value)
        log_max = math.log10(max_value)
        log_range = log_max - log_min
        
        # Store log scale parameters for hover detection
        self.log_min = log_min
        self.log_max = log_max
        self.log_range = log_range
        self.min_value = min_value
        self.max_value = max_value
        self.graph_height = graph_height
        self.margin_top = margin_top
        self.margin_bottom = margin_bottom
        
        # Draw grid lines and labels (logarithmic scale)
        num_grid_lines = 5
        for i in range(num_grid_lines):
            # Linear position in graph
            y = margin_top + (i * graph_height / (num_grid_lines - 1))
            
            # Grid line
            self.canvas.create_line(
                margin_left, y, width - margin_right, y,
                fill=self.colors['grid'], width=1 * self.dpi_scale, dash=(4, 4)
            )
            
            # Calculate log scale value for this grid line (inverted: top = max, bottom = min)
            log_value = log_max - (i / (num_grid_lines - 1)) * log_range
            value = 10 ** log_value
            
            # Y-axis label
            self.canvas.create_text(
                margin_left - 10, y,
                text=self.format_bytes(value) + "/s",
                anchor=tk.E,
                fill=self.colors['fg'],
                font=(self.mono_font, 10)
            )
        
        # Generate colors for processes (use a color palette)
        num_processes = len(process_histories)
        process_colors = {}
        for idx, proc_id in enumerate(sorted(process_histories.keys())):
            # Generate distinct colors using HSV color space
            hue = (idx * 0.618) % 1.0  # Golden ratio for better distribution
            saturation = 0.7
            value = 0.9
            rgb = colorsys.hsv_to_rgb(hue, saturation, value)
            process_colors[proc_id] = '#{:02x}{:02x}{:02x}'.format(
                int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
            )
        
        # Draw lines for each process (download and upload)
        for proc_id, proc_data in process_histories.items():
            download_history = proc_data['download']
            upload_history = proc_data['upload']
            proc_name = proc_data['name']
            color = process_colors[proc_id]
            
            # Draw download line
            if len(download_history) > 1:
                line_points = []
                data_points = []  # Store for hover detection
                
                for i, value in enumerate(download_history):
                    # X coordinate: evenly spaced across graph width
                    # i=0 -> x=margin_left (left edge), i=len-1 -> x=width-margin_right (right edge)
                    x = margin_left + (i * graph_width / max(len(download_history) - 1, 1))
                    # Y coordinate: logarithmic scale
                    # Clamp value to min_value to avoid log(0)
                    clamped_value = max(value, min_value)
                    log_value = math.log10(clamped_value)
                    # Normalize log value to 0-1 range, then scale to graph height
                    # Inverted: high values at top (y near margin_top), low values at bottom
                    normalized = (log_value - log_min) / log_range
                    y = margin_top + graph_height - (normalized * graph_height)
                    line_points.extend([x, y])
                    data_points.append((x, y, value, 'download', proc_name))
                
                # Draw the line
                if len(line_points) >= 4:
                    line_id = self.canvas.create_line(
                        line_points,
                        fill=color,
                        width=2 * self.dpi_scale,
                        tags=('download_line', proc_id)
                    )
                    # Store data points for hover detection
                    self.hover_data_points.append({
                        'line_id': line_id,
                        'points': data_points,
                        'proc_name': proc_name,
                        'type': 'download',
                        'color': color
                    })
            
            # Draw upload line (dashed style)
            if len(upload_history) > 1:
                line_points = []
                data_points = []  # Store for hover detection
                
                for i, value in enumerate(upload_history):
                    # X coordinate: evenly spaced across graph width (same as download)
                    # i=0 -> x=margin_left (left edge), i=len-1 -> x=width-margin_right (right edge)
                    x = margin_left + (i * graph_width / max(len(upload_history) - 1, 1))
                    # Y coordinate: logarithmic scale (same as download)
                    # Clamp value to min_value to avoid log(0)
                    clamped_value = max(value, min_value)
                    log_value = math.log10(clamped_value)
                    # Normalize log value to 0-1 range, then scale to graph height
                    # Inverted: high values at top (y near margin_top), low values at bottom
                    normalized = (log_value - log_min) / log_range
                    y = margin_top + graph_height - (normalized * graph_height)
                    line_points.extend([x, y])
                    data_points.append((x, y, value, 'upload', proc_name))
                
                # Draw the line with dashed style
                if len(line_points) >= 4:
                    line_id = self.canvas.create_line(
                        line_points,
                        fill=color,
                        width=2 * self.dpi_scale,
                        dash=(8, 4),
                        tags=('upload_line', proc_id)
                    )
                    # Store data points for hover detection
                    self.hover_data_points.append({
                        'line_id': line_id,
                        'points': data_points,
                        'proc_name': proc_name,
                        'type': 'upload',
                        'color': color
                    })
        
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
            width / 2, height - 12,
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
        self.history['timestamp'] = deque(maxlen=60)  # Reinitialize timestamp deque
    
    def on_mouse_move(self, event):
        """Handle mouse movement for hover tooltips"""
        # Graph dimensions (must match draw_graph exactly)
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        margin_left = 80
        margin_right = 20
        margin_top = 20
        margin_bottom = 30
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        # Check if mouse is within graph bounds
        # Also ensure we're not interfering with control_frame buttons
        if event.x < margin_left or event.x > width - margin_right or \
           event.y < margin_top or event.y > height - margin_bottom:
            self.hide_highlights()
            self.hide_tooltip()
            return
        
        # Get canvas position relative to root window to ensure we're not overlapping control_frame
        try:
            canvas_y = self.canvas.winfo_rooty()
            control_frame_y = self.control_frame.winfo_rooty()
            control_frame_height = self.control_frame.winfo_height()
            mouse_y_root = event.y_root if hasattr(event, 'y_root') else None
            
            # If mouse is in control_frame area, don't process (let buttons handle it)
            if mouse_y_root and control_frame_y <= mouse_y_root <= control_frame_y + control_frame_height:
                self.hide_highlights()
                self.hide_tooltip()
                return
        except:
            pass  # If we can't determine positions, continue normally
        
        # Need data points to show tooltips
        if not self.hover_data_points:
            return
        
        # Find the single closest data point overall (by 2D distance, accounting for log scale)
        mouse_x = event.x
        mouse_y = event.y
        
        # Convert mouse Y position to log value for accurate comparison on log scale
        # Formula: y = margin_top + graph_height - (normalized * graph_height)
        # Solving for normalized: normalized = (margin_top + graph_height - y) / graph_height
        # Then: log_value = log_min + normalized * log_range
        mouse_y_normalized = (self.margin_top + self.graph_height - mouse_y) / self.graph_height
        mouse_y_normalized = max(0.0, min(1.0, mouse_y_normalized))  # Clamp to [0, 1]
        mouse_log_value = self.log_min + mouse_y_normalized * self.log_range
        
        closest_point = None
        min_distance_squared = float('inf')
        
        # Find the closest point by combining X distance (pixels) and Y distance (log scale)
        # Use squared distance to avoid sqrt calculations
        for line_data in self.hover_data_points:
            for x, y, value, direction, proc_name in line_data['points']:
                # Calculate X distance (pixel distance)
                dx = mouse_x - x
                
                # Calculate Y distance using log scale
                clamped_value = max(value, self.min_value)
                point_log_value = math.log10(clamped_value)
                # Convert log distance to a normalized distance for comparison
                # Scale log distance by graph_height to make it comparable to pixel distance
                log_distance_normalized = abs(mouse_log_value - point_log_value) * (self.graph_height / self.log_range)
                
                # Calculate combined distance squared (weight X and Y equally)
                distance_squared = dx * dx + log_distance_normalized * log_distance_normalized
                
                if distance_squared < min_distance_squared:
                    min_distance_squared = distance_squared
                    closest_point = {
                        'x': x,
                        'y': y,
                        'value': value,
                        'direction': direction,
                        'proc_name': proc_name,
                        'color': line_data['color']
                    }
        
        # Show tooltip and highlights if we found a point
        if closest_point:
            self.show_highlights(closest_point)
            self.show_tooltip(event.x, event.y, closest_point)
        else:
            self.hide_highlights()
            self.hide_tooltip()
    
    def on_mouse_leave(self, event):
        """Hide tooltip when mouse leaves canvas"""
        self.hide_highlights()
        self.hide_tooltip()
    
    def show_highlights(self, closest_point_data):
        """Highlight the single closest marker to the cursor"""
        # Remove existing highlights
        self.hide_highlights()
        
        if not closest_point_data:
            return
        
        # Highlight only the closest point with a larger, brighter circle
        circle_id = self.canvas.create_oval(
            closest_point_data['x'] - 6, closest_point_data['y'] - 6,
            closest_point_data['x'] + 6, closest_point_data['y'] + 6,
            fill=closest_point_data['color'],
            outline='white',
            width=2,
            tags='hover_highlight'
        )
        self.hover_highlights.append(circle_id)
    
    def hide_highlights(self):
        """Hide all highlight markers"""
        if self.hover_highlights:
            for highlight_id in self.hover_highlights:
                try:
                    self.canvas.delete(highlight_id)
                except:
                    pass
            self.hover_highlights = []
        else:
            # Also clean up any orphaned highlights
            self.canvas.delete('hover_highlight')
    
    def show_tooltip(self, x, y, point_data):
        """Show tooltip with process information"""
        # Remove existing tooltip
        self.hide_tooltip()
        
        # Create tooltip text
        direction_symbol = "↓" if point_data['direction'] == 'download' else "↑"
        tooltip_text = f"{point_data['proc_name']}\n{direction_symbol} {self.format_bytes(point_data['value'])}/s"
        
        # Ensure tooltip stays within canvas bounds
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # Create temporary text item to measure actual dimensions
        temp_text_id = self.canvas.create_text(
            0, 0,
            text=tooltip_text,
            anchor=tk.NW,
            font=(self.main_font, 10, 'bold'),
            tags='temp_measure'
        )
        bbox = self.canvas.bbox(temp_text_id)
        text_width = bbox[2] - bbox[0] if bbox else len(tooltip_text.split('\n')[0]) * 7
        text_height = bbox[3] - bbox[1] if bbox else 30
        self.canvas.delete('temp_measure')
        
        # Calculate tooltip position (above the point, offset to avoid cursor)
        padding = 8
        tooltip_x = point_data['x']
        tooltip_y = point_data['y'] - text_height - padding * 2 - 10  # Position above point
        
        # Adjust tooltip position to stay within bounds
        if tooltip_x + text_width + padding > canvas_width - 10:
            tooltip_x = canvas_width - text_width - padding - 10
        if tooltip_x < padding + 10:
            tooltip_x = padding + 10
        
        if tooltip_y < padding + 10:
            # Not enough space above, position below instead
            tooltip_y = point_data['y'] + 10
        
        # Create tooltip background rectangle (positioned around text)
        bg_x1 = tooltip_x - padding
        bg_y1 = tooltip_y - padding
        bg_x2 = tooltip_x + text_width + padding
        bg_y2 = tooltip_y + text_height + padding
        
        bg_id = self.canvas.create_rectangle(
            bg_x1, bg_y1,
            bg_x2, bg_y2,
            fill='#2d2d2d',
            outline=point_data['color'],
            width=2,
            tags='tooltip'
        )
        
        # Create tooltip text (aligned to top-left of background with padding)
        text_id = self.canvas.create_text(
            tooltip_x, tooltip_y,
            text=tooltip_text,
            anchor=tk.NW,
            fill=self.colors['fg'],
            font=(self.main_font, 10, 'bold'),
            tags='tooltip'
        )
        
        # Note: The dot is now handled by show_highlights() for better visual consistency
        self.hover_tooltip = {'bg': bg_id, 'text': text_id}
    
    def hide_tooltip(self):
        """Hide the tooltip"""
        if self.hover_tooltip:
            self.canvas.delete('tooltip')
            self.hover_tooltip = None
    
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

