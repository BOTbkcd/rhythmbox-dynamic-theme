"""
GTK theme management for Rhythm-Hue plugin.

This module handles CSS generation and application to Rhythmbox UI.
"""

import logging
from typing import Optional
from gi.repository import Gtk, Gdk, GLib
from color_extractor import ColorPalette
from config import PluginConfiguration

logger = logging.getLogger('rhythm-hue.theme-manager')


class ThemeManager:
    """
    Manages GTK CSS theme application and transitions.

    Generates dynamic CSS from color palettes and applies them to Rhythmbox UI.
    """

    def __init__(self, config: PluginConfiguration):
        """
        Initialize theme manager.

        Args:
            config: Plugin configuration
        """
        self.config = config
        self.css_provider: Optional[Gtk.CssProvider] = None
        self.is_active = False
        self.gradient_timer_id: Optional[int] = None
        self.current_gradient_state: int = 0
        self.current_palette: Optional[ColorPalette] = None

        logger.info("ThemeManager initialized")

    def apply_theme(self, palette: ColorPalette, transition: bool = True) -> None:
        """
        Apply color palette to Rhythmbox UI.

        Args:
            palette: ColorPalette to apply
            transition: Whether to animate transition (default True)
        """
        try:
            # Store palette for gradient cycling
            self.current_palette = palette
            self.current_gradient_state = 0

            # Stop existing timer if any
            if self.gradient_timer_id is not None:
                GLib.source_remove(self.gradient_timer_id)
                self.gradient_timer_id = None

            # Generate CSS from palette
            css = self.generate_css(palette)

            # Create or update CSS provider
            if self.css_provider is None:
                self.css_provider = Gtk.CssProvider()

            # Load CSS
            self.css_provider.load_from_data(css.encode('utf-8'))

            # Get default screen
            screen = Gdk.Screen.get_default()
            if screen is None:
                logger.error("Could not get default screen")
                return

            # Apply to screen with user priority (higher than APPLICATION)
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                self.css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

            self.is_active = True

            # Start gradient cycling timer
            self.gradient_timer_id = GLib.timeout_add_seconds(25, self._cycle_gradient)

            logger.info(f"Theme applied successfully (transition={transition})")

        except Exception as e:
            logger.error(f"Error applying theme: {e}", exc_info=True)

    def remove_theme(self) -> None:
        """
        Remove custom theme and restore default.
        """
        try:
            # Stop gradient cycling timer
            if self.gradient_timer_id is not None:
                GLib.source_remove(self.gradient_timer_id)
                self.gradient_timer_id = None

            if self.css_provider is not None:
                screen = Gdk.Screen.get_default()
                if screen is not None:
                    Gtk.StyleContext.remove_provider_for_screen(
                        screen,
                        self.css_provider
                    )

            self.css_provider = None
            self.is_active = False
            self.current_palette = None
            logger.info("Theme removed successfully")

        except Exception as e:
            logger.error(f"Error removing theme: {e}", exc_info=True)

    def _cycle_gradient(self) -> bool:
        """
        Timer callback to cycle through gradient states.

        Returns:
            True to continue timer, False to stop
        """
        if self.current_palette is None or not self.is_active:
            return False

        # Cycle to next state (0, 1, 2,.. then back to 0)
        self.current_gradient_state = (self.current_gradient_state + 1) % 9

        try:
            # Regenerate CSS with new gradient state
            css = self.generate_css(self.current_palette)

            if self.css_provider is not None:
                self.css_provider.load_from_data(css.encode('utf-8'))
                logger.debug(f"Gradient cycled to state {self.current_gradient_state}")
        except Exception as e:
            logger.error(f"Error cycling gradient: {e}", exc_info=True)

        return True  # Continue timer

    def generate_css(self, palette: ColorPalette) -> str:
        """
        Generate CSS stylesheet from color palette.

        Args:
            palette: ColorPalette with colors

        Returns:
            CSS stylesheet string
        """
        # Convert RGB tuples to CSS format
        def rgb_to_css(rgb):
            return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"

        def rgb_to_rgba(rgb, alpha):
            return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"

        # Base colors
        primary = rgb_to_css(palette.primary)
        secondary = rgb_to_css(palette.secondary)
        background = rgb_to_css(palette.background)
        foreground = rgb_to_css(palette.foreground)
        accent = rgb_to_css(palette.accent)

        # Common color variations with opacity - reusable across CSS
        primary_5 = rgb_to_rgba(palette.primary, 0.05)    # Very subtle background
        primary_10 = rgb_to_rgba(palette.primary, 0.1)    # Subtle background
        primary_15 = rgb_to_rgba(palette.primary, 0.15)   
        primary_20 = rgb_to_rgba(palette.primary, 0.2)    
        primary_30 = rgb_to_rgba(palette.primary, 0.3)    
        primary_50 = rgb_to_rgba(palette.primary, 0.5)    

        accent_30 = rgb_to_rgba(palette.accent, 0.3)

        # Get transition duration from config
        transition_duration = self.config.transition_duration

        # Build CSS based on enabled UI elements
        css_parts = []

        # Base transition for smooth changes
        css_parts.append(f"""
* {{
    transition: background {transition_duration}s ease,
                background-color {transition_duration}s ease,
                color {transition_duration}s ease,
                border-color {transition_duration}s ease;
}}
""")

        # Window background
        if self.config.theme_background:
            # Create gradient from background (darker) to primary (lighter/saturated)
            # Apply to top-level window only - all children will be transparent to show it through

            # Create solid RGB blended colors (not RGBA with transparency)
            # Blend background with primary at different intensities
            def blend_colors(bg_rgb, pr_rgb, mix):
                """Blend two colors: mix=0 is pure bg, mix=1 is pure primary"""
                return rgb_to_css((
                    int(bg_rgb[0] * (1 - mix) + pr_rgb[0] * mix),
                    int(bg_rgb[1] * (1 - mix) + pr_rgb[1] * mix),
                    int(bg_rgb[2] * (1 - mix) + pr_rgb[2] * mix)
                ))

            blend_30 = blend_colors(palette.background, palette.primary, 0.3)
            secondary_blend_30 = blend_colors(palette.background, palette.secondary, 0.3)
            foreground_blend_15 = blend_colors(palette.background, palette.foreground, 0.15)
            foreground_primary_blend = blend_colors(palette.primary, palette.foreground, 0.5)

            # Define radial gradient positions that will be cycled through via timer
            gradient_positions = [
                "100% 100%",
                "65% 100%",
                "15% 84%",
                "0% 55%",
                "5% 5%",
                "35% 0%",
                "65% 0%",
                "100% 20%",
                "100% 80%",   
            ]

            # Use current gradient position for this render
            current_position = gradient_positions[self.current_gradient_state]

            css_parts.append(f"""
/* Radial gradient with moving center - manually cycled via Python timer */
window,
.rhythmbox-window,
window.background,
window#RBShell {{
    background: radial-gradient(ellipse at {current_position}, {foreground_blend_15}7%, {blend_30} 25%, {secondary_blend_30} 42%, {background} 65%);
    background-color: {background};
    color: {foreground};
    transition: background 5s ease-in-out;
}}

/* Make ALL container elements transparent so gradient shows through */
box,
grid,
paned,
scrolledwindow,
scrolledwindow.frame,
viewport {{
    background-color: transparent;
}}

/* Main content area - song list (transparent to show gradient) */
treeview,
treeview.view,
.view {{
    background-color: transparent;
    color: {foreground};
}}

treeview:selected,
treeview.view:selected {{
    background-color: {primary_50};
    color: {foreground};
}}

/* Column headers with semi-transparent background */
treeview header button,
treeview.view header button {{
    background-color: {primary_50};
    color: {foreground};
    border: none;
    border-radius: 0;
    font-weight: normal;
}}

treeview header button:hover,
treeview.view header button:hover {{
    background-color: {primary_30};
}}

/* Scrolled windows transparent to show gradient */
treeview.view>* {{
    background-color: transparent;
}}
""")

        # Toolbar
        if self.config.theme_toolbar:
            css_parts.append(f"""
window toolbar {{
    background-color: transparent;
    color: {foreground};
    border: none;
    box-shadow: 0px 0px 20px 15px {primary_50};
    border-radius: 0;
}}

window popover {{
    background-color: #222222;
    color: {primary}
}}

.sidebar-toolbar {{
    box-shadow: none;
}}

window headerbar {{
    background-color: {background};
    transition-property: background-color;
    transition-duration: 5s;
    transition-timing-function: ease-in-out;
}}

window headerbar button {{
    background-color: {primary_20};
    color: {foreground};
    border: none;
}}

window headerbar button:hover {{
    background-color: {primary_30};
}}
""")

        # Sidebar
        if self.config.theme_sidebar:
            css_parts.append(f"""
.sidebar,
.sidebar-row,
placessidebar {{
    background-color: transparent;
    color: {foreground};
}}

.sidebar-row:selected,
placessidebar row:selected {{
    background-color: {primary_50};
    color: {foreground};
}}
""")

        # Progress bar
        if self.config.theme_progress_bar:
            css_parts.append(f"""
/* Player progress bar scale - all possible selectors */
scale trough {{
    border: 1px solid {primary};
    min-height: 6px;
}}

scale trough highlight,
scale trough progress {{
    border: none;
    background: {primary};
    box-shadow: 0px 0px 8px 3px {primary};
}}

scale slider {{
    background-color: {foreground_primary_blend};
    box-shadow: 0px 0px 5px 1px {foreground};
    border: none;
}}
""")

        # Buttons and interactive elements
        css_parts.append(f"""
window button {{
    background-color: {primary_15};
    background-image: none;
    color: {foreground};
    border: 1px solid {primary};
}}

window button:hover {{
    background-color: {accent_30};
}}

window toolbar button,
window button:active,
window button:checked {{
    background-color: {primary_50};
    border: none;
    color: {foreground};
}}
""")

        # Additional UI elements
        css_parts.append(f"""
/* Player control bar at bottom */
.bottom-bar,
#player-bar,
actionbar {{
    background-color: transparent;
    background-image: none;
    color: {foreground};
    border-top: 1px solid {primary_5};
}}

/* Scrollbars */
scrollbar {{
    background-color: {primary_20};
    border-radius: 10px;
}}

scrollbar slider {{
    background-color: transparent;
    min-height: 8px;
}}

scrollbar slider:hover {{
    background-color: {primary_50};
}}

scrollbar.overlay-indicator:not(.dragging):not(.hovering) slider {{
    background-color: {primary_30};
}}

/* Menus */
menu,
menubar {{
    background-color: transparent;
    color: {foreground};
}}

menuitem:hover {{
    background-color: {primary_50};
}}

/* Tooltips - keep opaque for readability */
tooltip {{
    background-color: {background};
    color: {foreground};
    border: 1px solid {primary};
}}

/* Search bar container and surrounding boxes */
searchbar,
searchbar box.horizontal {{
    background-color: transparent;
    border: none;
}}

/* Search bar icons */
searchbar image {{
    color: {foreground}
}}

/* Entry fields (search, etc) */
entry {{
    background-color: {primary_10};
    color: {foreground};
    border: 1px solid {primary};
}}

entry:focus {{
    border-color: {accent};
    background-color: {primary_20};
}}

/* Text views and lyrics panel - transparent to show gradient */
textview,
textview text {{
    background-color: transparent;
}}

.view text,
text {{
    background-color: transparent;
    color: {foreground};
    transition-property: color;
    transition-duration: 5s;
    transition-timing-function: ease-in-out;
}}
""")

        return '\n'.join(css_parts)

    def is_theme_active(self) -> bool:
        """Check if custom theme is currently active."""
        return self.is_active
