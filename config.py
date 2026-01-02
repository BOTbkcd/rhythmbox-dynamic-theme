"""
Configuration management for Rhythm-Hue plugin.

This module provides hardcoded configuration values for the plugin.
"""

from typing import Any


class PluginConfiguration:
    """Manages plugin settings with hardcoded defaults."""

    def __init__(self):
        """Initialize configuration with default values."""
        # Configuration values
        self._color_intensity: float = 1.0
        self._transition_duration: float = 0.3
        self._theme_background: bool = True
        self._theme_toolbar: bool = True
        self._theme_sidebar: bool = True
        self._theme_progress_bar: bool = True
        self._cache_size: int = 128
        self._debounce_delay: float = 0.3

        # Default palette colors (fallback when album art is missing)
        self._default_primary: str = '#C00048'
        self._default_secondary: str = '#c00048'
        self._default_background: str = '#152238'
        self._default_foreground: str = '#f0f0f0'
        self._default_accent: str = '#C00048'

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

    @property
    def default_secondary(self) -> str:
        """Default secondary color (hex string)."""
        return self._default_secondary

    @property
    def default_background(self) -> str:
        """Default background color (hex string)."""
        return self._default_background

    @property
    def default_foreground(self) -> str:
        """Default foreground color (hex string)."""
        return self._default_foreground

    @property
    def default_accent(self) -> str:
        """Default accent color (hex string)."""
        return self._default_accent
