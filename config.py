"""
Configuration management for Rhythm-Hue plugin.

This module provides configuration values for the plugin with GSettings persistence.
"""

from typing import Any
from gi.repository import Gio


class PluginConfiguration:
    """Manages plugin settings with GSettings persistence."""

    GSETTINGS_SCHEMA = 'org.gnome.rhythmbox.plugins.rhythmbox-dynamic-theme'

    def __init__(self):
        """Initialize configuration with default values and GSettings."""
        # Initialize GSettings
        try:
            self._settings = Gio.Settings.new(self.GSETTINGS_SCHEMA)
        except Exception:
            # Fallback if GSettings schema is not installed
            self._settings = None

        # Configuration values (hardcoded, not persisted)
        self._color_intensity: float = 1.0
        self._transition_duration: float = 0.3
        self._theme_background: bool = True
        self._theme_toolbar: bool = True
        self._theme_sidebar: bool = True
        self._theme_progress_bar: bool = True
        self._cache_size: int = 128
        self._debounce_delay: float = 0.3

        # Default palette colors (fallback when album art is missing)
        # Load from GSettings or use hardcoded defaults
        if self._settings:
            self._default_primary: str = self._settings.get_string('default-primary')
            self._default_secondary: str = self._settings.get_string('default-secondary')
            self._default_background: str = self._settings.get_string('default-background')
            self._default_foreground: str = self._settings.get_string('default-foreground')
            self._default_accent: str = self._settings.get_string('default-accent')
        else:
            self._default_primary: str = '#9e0d43'
            self._default_secondary: str = '#305b82'
            self._default_background: str = '#04040a'
            self._default_foreground: str = '#f0f0f0'
            self._default_accent: str = '#9e0d43'

    @property
    def color_intensity(self) -> float:
        """Color intensity multiplier (0.5 - 2.0)."""
        return self._color_intensity

    @color_intensity.setter
    def color_intensity(self, value: float):
        if not 0.5 <= value <= 2.0:
            raise ValueError("color_intensity must be between 0.5 and 2.0")
        self._color_intensity = value

    @property
    def transition_duration(self) -> float:
        """Theme transition duration in seconds (0.1 - 2.0)."""
        return self._transition_duration

    @transition_duration.setter
    def transition_duration(self, value: float):
        if not 0.1 <= value <= 2.0:
            raise ValueError("transition_duration must be between 0.1 and 2.0")
        self._transition_duration = value

    @property
    def theme_background(self) -> bool:
        """Apply theme to window background."""
        return self._theme_background

    @theme_background.setter
    def theme_background(self, value: bool):
        self._theme_background = value

    @property
    def theme_toolbar(self) -> bool:
        """Apply theme to toolbar."""
        return self._theme_toolbar

    @theme_toolbar.setter
    def theme_toolbar(self, value: bool):
        self._theme_toolbar = value

    @property
    def theme_sidebar(self) -> bool:
        """Apply theme to sidebar."""
        return self._theme_sidebar

    @theme_sidebar.setter
    def theme_sidebar(self, value: bool):
        self._theme_sidebar = value

    @property
    def theme_progress_bar(self) -> bool:
        """Apply theme to progress bar."""
        return self._theme_progress_bar

    @theme_progress_bar.setter
    def theme_progress_bar(self, value: bool):
        self._theme_progress_bar = value

    @property
    def cache_size(self) -> int:
        """Maximum cached color palettes (16 - 512)."""
        return self._cache_size

    @cache_size.setter
    def cache_size(self, value: int):
        if not 16 <= value <= 512:
            raise ValueError("cache_size must be between 16 and 512")
        self._cache_size = value

    @property
    def debounce_delay(self) -> float:
        """Debounce delay in seconds (0.1 - 1.0)."""
        return self._debounce_delay

    @debounce_delay.setter
    def debounce_delay(self, value: float):
        if not 0.1 <= value <= 1.0:
            raise ValueError("debounce_delay must be between 0.1 and 1.0")
        self._debounce_delay = value

    
    # Default palette colors

    @property
    def default_primary(self) -> str:
        """Default primary color (hex string)."""
        return self._default_primary

    @default_primary.setter
    def default_primary(self, value: str):
        if not self._is_valid_hex_color(value):
            raise ValueError("default_primary must be a valid hex color (e.g., '#9e0d43')")
        self._default_primary = value
        if self._settings:
            self._settings.set_string('default-primary', value)

    @property
    def default_secondary(self) -> str:
        """Default secondary color (hex string)."""
        return self._default_secondary

    @default_secondary.setter
    def default_secondary(self, value: str):
        if not self._is_valid_hex_color(value):
            raise ValueError("default_secondary must be a valid hex color (e.g., '#305b82')")
        self._default_secondary = value
        if self._settings:
            self._settings.set_string('default-secondary', value)

    @property
    def default_background(self) -> str:
        """Default background color (hex string)."""
        return self._default_background

    @default_background.setter
    def default_background(self, value: str):
        if not self._is_valid_hex_color(value):
            raise ValueError("default_background must be a valid hex color (e.g., '#04040a')")
        self._default_background = value
        if self._settings:
            self._settings.set_string('default-background', value)

    @property
    def default_foreground(self) -> str:
        """Default foreground color (hex string)."""
        return self._default_foreground

    @default_foreground.setter
    def default_foreground(self, value: str):
        if not self._is_valid_hex_color(value):
            raise ValueError("default_foreground must be a valid hex color (e.g., '#f0f0f0')")
        self._default_foreground = value
        if self._settings:
            self._settings.set_string('default-foreground', value)

    @property
    def default_accent(self) -> str:
        """Default accent color (hex string)."""
        return self._default_accent

    @default_accent.setter
    def default_accent(self, value: str):
        if not self._is_valid_hex_color(value):
            raise ValueError("default_accent must be a valid hex color (e.g., '#9e0d43')")
        self._default_accent = value
        if self._settings:
            self._settings.set_string('default-accent', value)

    @staticmethod
    def _is_valid_hex_color(color: str) -> bool:
        """Validate hex color format."""
        if not isinstance(color, str):
            return False
        if not color.startswith('#'):
            return False
        if len(color) != 7:
            return False
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
