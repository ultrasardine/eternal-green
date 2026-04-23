"""Settings window for eternal-green tray application.

Provides a tkinter-based settings dialog that can be opened
from the system tray menu to edit all configuration options.

tkinter is imported lazily so the module can be loaded in
headless / CI environments without a display server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Callable

from eternal_green.config import ConfigManager, EternalGreenConfig

if TYPE_CHECKING:
    import tkinter as tk


class SettingsWindow:
    """Tkinter settings dialog for editing eternal-green configuration."""

    WINDOW_TITLE = "Eternal Green — Settings"
    WINDOW_WIDTH = 420
    WINDOW_HEIGHT = 400
    PADDING = 12

    def __init__(
        self,
        config_manager: ConfigManager,
        on_save: Optional[Callable[[EternalGreenConfig], None]] = None,
    ):
        """Initialize settings window.

        Args:
            config_manager: Configuration manager for loading/saving.
            on_save: Optional callback invoked with the new config after save.
        """
        self.config_manager = config_manager
        self.on_save = on_save
        self._window: Optional[tk.Tk] = None

        # Widget references set during _build_ui
        self._interval_var: Any = None
        self._pixels_var: Any = None
        self._silent_var: Any = None
        self._random_var: Any = None
        self._range_min_var: Any = None
        self._range_max_var: Any = None
        self._range_min_spin: Any = None
        self._range_max_spin: Any = None
        self._log_var: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the settings window (creates a new Tk root)."""
        import tkinter as tk

        if self._window is not None:
            try:
                self._window.lift()
                self._window.focus_force()
                return
            except tk.TclError:
                self._window = None

        config = self.config_manager.load()

        root = tk.Tk()
        root.title(self.WINDOW_TITLE)
        root.resizable(False, False)

        # Center on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth() - self.WINDOW_WIDTH) // 2
        y = (root.winfo_screenheight() - self.WINDOW_HEIGHT) // 2
        root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

        self._window = root
        self._build_ui(root, config)

        # Bring to front on macOS
        root.attributes("-topmost", True)
        root.after(100, lambda: root.attributes("-topmost", False))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.mainloop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, root: tk.Tk, config: EternalGreenConfig) -> None:
        """Build all UI widgets."""
        import tkinter as tk
        from tkinter import ttk

        pad = self.PADDING

        main_frame = ttk.Frame(root, padding=pad)
        main_frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # --- Interval ---
        ttk.Label(main_frame, text="Interval (seconds):").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 4)
        )
        self._interval_var = tk.IntVar(value=config.interval_seconds)
        ttk.Spinbox(
            main_frame,
            from_=10,
            to=3600,
            textvariable=self._interval_var,
            width=10,
        ).grid(row=row, column=1, sticky=tk.E, pady=(0, 4))
        row += 1

        # --- Movement pixels ---
        ttk.Label(main_frame, text="Movement (pixels):").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 4)
        )
        self._pixels_var = tk.IntVar(value=config.movement_pixels)
        ttk.Spinbox(
            main_frame,
            from_=1,
            to=100,
            textvariable=self._pixels_var,
            width=10,
        ).grid(row=row, column=1, sticky=tk.E, pady=(0, 4))
        row += 1

        # --- Silent mode ---
        self._silent_var = tk.BooleanVar(value=config.silent_mode)
        ttk.Checkbutton(
            main_frame, text="Silent mode (mouse only)", variable=self._silent_var
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(4, 4))
        row += 1

        # --- Random interval ---
        self._random_var = tk.BooleanVar(value=config.random_interval)
        ttk.Checkbutton(
            main_frame,
            text="Random interval",
            variable=self._random_var,
            command=self._toggle_range_state,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(4, 4))
        row += 1

        # --- Range min ---
        ttk.Label(main_frame, text="Range min (seconds):").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 4)
        )
        self._range_min_var = tk.IntVar(value=config.interval_range_min)
        self._range_min_spin = ttk.Spinbox(
            main_frame,
            from_=10,
            to=3600,
            textvariable=self._range_min_var,
            width=10,
        )
        self._range_min_spin.grid(row=row, column=1, sticky=tk.E, pady=(0, 4))
        row += 1

        # --- Range max ---
        ttk.Label(main_frame, text="Range max (seconds):").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 4)
        )
        self._range_max_var = tk.IntVar(value=config.interval_range_max)
        self._range_max_spin = ttk.Spinbox(
            main_frame,
            from_=10,
            to=3600,
            textvariable=self._range_max_var,
            width=10,
        )
        self._range_max_spin.grid(row=row, column=1, sticky=tk.E, pady=(0, 4))
        row += 1

        # --- Log file path ---
        ttk.Label(main_frame, text="Log file:").grid(
            row=row, column=0, sticky=tk.W, pady=(4, 4)
        )
        row += 1

        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)

        self._log_var = tk.StringVar(value=config.log_file_path)
        ttk.Entry(log_frame, textvariable=self._log_var).grid(
            row=0, column=0, sticky=tk.EW, padx=(0, 4)
        )
        ttk.Button(log_frame, text="Browse…", command=self._browse_log).grid(
            row=0, column=1
        )
        row += 1

        # --- Buttons ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky=tk.E, pady=(12, 0))

        ttk.Button(btn_frame, text="Cancel", command=self._on_close).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side=tk.RIGHT)

        # Make columns stretch
        main_frame.columnconfigure(1, weight=1)

        # Set initial range-spin state
        self._toggle_range_state()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _toggle_range_state(self) -> None:
        """Enable/disable range spinboxes based on random-interval toggle."""
        state = "normal" if self._random_var.get() else "disabled"
        self._range_min_spin.configure(state=state)
        self._range_max_spin.configure(state=state)

    def _browse_log(self) -> None:
        """Open a file dialog to choose a log file path."""
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Choose log file location",
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
        )
        if path:
            self._log_var.set(path)

    def _on_save(self) -> None:
        """Validate and save configuration."""
        from tkinter import messagebox

        try:
            new_config = self.config_manager.update(
                interval_seconds=self._interval_var.get(),
                movement_pixels=self._pixels_var.get(),
                silent_mode=self._silent_var.get(),
                random_interval=self._random_var.get(),
                interval_range_min=self._range_min_var.get(),
                interval_range_max=self._range_max_var.get(),
                log_file_path=self._log_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Validation Error", str(exc), parent=self._window)
            return

        if self.on_save:
            self.on_save(new_config)

        self._on_close()

    def _on_close(self) -> None:
        """Destroy the window."""
        if self._window is not None:
            self._window.destroy()
            self._window = None


def _run_standalone() -> None:
    """Open the settings window as a standalone process.

    Called when this module is executed directly via
    ``python -m eternal_green.settings_window`` or ``sys.executable -m …``.
    The window writes config changes through ConfigManager and exits.
    """
    config_manager = ConfigManager()
    window = SettingsWindow(config_manager)
    window.open()


if __name__ == "__main__":
    _run_standalone()
