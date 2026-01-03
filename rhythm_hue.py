"""
Main plugin module for Rhythmbox Dynamic Theme.

This module implements the Rhythmbox plugin interface and coordinates
color extraction, caching, and theme application.
"""

import hashlib
import logging
import os
import tempfile
import urllib.parse
from typing import Optional
from gi.repository import GObject, Peas, PeasGtk, RB, Gtk, Gdk
from color_extractor import ColorPalette, extract_colors_async, extract_colors_sync
from theme_manager import ThemeManager
from color_cache import ColorCache
from config import PluginConfiguration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('rhythmbox-dynamic-theme')


class RhythmHuePlugin(GObject.Object, Peas.Activatable, PeasGtk.Configurable):
    """
    Rhythmbox plugin that dynamically themes UI based on album art colors.

    Implements the Peas.Activatable interface for plugin lifecycle management and PeasGtk.Configurable for preferences dialog.
    """

    __gtype_name__ = 'RhythmHuePlugin'
    object = GObject.Property(type=GObject.Object)

    def __init__(self):
        """Initialize plugin instance."""
        super().__init__()
        self.config: Optional[PluginConfiguration] = None
        self.theme_manager: Optional[ThemeManager] = None
        self.color_cache: Optional[ColorCache] = None
        self.player: Optional[RB.ShellPlayer] = None
        self.signal_ids = []
        self.pending_extraction = False
        self.debounce_timer_id = None
        self.temp_art_files = []  # Track temp files for cleanup

        logger.info("RhythmHuePlugin instance created")

    def do_activate(self) -> None:
        """
        Called when plugin is enabled.

        Initializes all components and connects to Rhythmbox signals.
        """
        try:
            logger.info("Activating Rhythmbox Dynamic Theme plugin...")

            # Initialize configuration
            self.config = PluginConfiguration()

            # Initialize theme manager
            self.theme_manager = ThemeManager(self.config)

            # Initialize color cache
            cache_size = self.config.cache_size
            self.color_cache = ColorCache(max_size=cache_size)

            # Get Rhythmbox shell and player
            shell = self.object
            self.player = shell.props.shell_player

            # Connect to player signals
            signal_id = self.player.connect('playing-song-changed', self.on_playing_song_changed)
            self.signal_ids.append(signal_id)

            logger.info("Rhythmbox Dynamic Theme plugin activated successfully")

            # Apply theme to currently playing song
            self.apply_theme_to_current_song()

        except Exception as e:
            logger.error(f"Error activating plugin: {e}", exc_info=True)

    def do_deactivate(self) -> None:
        """
        Called when plugin is disabled.

        Cleans up resources and removes theme.
        """
        try:
            logger.info("Deactivating Rhythmbox Dynamic Theme plugin...")

            # Cancel any pending debounce timer
            if self.debounce_timer_id is not None:
                GObject.source_remove(self.debounce_timer_id)
                self.debounce_timer_id = None

            # Disconnect all signals
            if self.player:
                for signal_id in self.signal_ids:
                    self.player.disconnect(signal_id)
            self.signal_ids.clear()

            # Remove theme
            if self.theme_manager:
                self.theme_manager.remove_theme()

            # Clear cache
            if self.color_cache:
                self.color_cache.clear()

            # Clean up temp files
            self._cleanup_temp_files()

            logger.info("Rhythmbox Dynamic Theme plugin deactivated successfully")

        except Exception as e:
            logger.error(f"Error deactivating plugin: {e}", exc_info=True)

    def on_playing_song_changed(self, player: RB.ShellPlayer, entry: RB.RhythmDBEntry) -> None:
        """
        Handle song change events.

        Args:
            player: The RB.ShellPlayer instance
            entry: New playing song entry (or None if stopped)
        """
        try:
            # Cancel any pending debounce timer
            if self.debounce_timer_id is not None:
                GObject.source_remove(self.debounce_timer_id)
                self.debounce_timer_id = None

            if entry is None:
                logger.info("Playback stopped, applying default theme")
                self._apply_default_theme()
                return

            # Debounce rapid song changes
            debounce_delay = int(self.config.debounce_delay * 1000)  # Convert to milliseconds
            self.debounce_timer_id = GObject.timeout_add(
                debounce_delay,
                lambda: self._process_song_change(entry) or False
            )

        except Exception as e:
            logger.error(f"Error handling song change: {e}", exc_info=True)

    def _process_song_change(self, entry: RB.RhythmDBEntry) -> None:
        """
        Process song change after debounce period.

        Args:
            entry: RhythmDBEntry for the new song
        """
        try:
            self.debounce_timer_id = None

            # Extract song metadata
            title = entry.get_string(RB.RhythmDBPropType.TITLE)
            artist = entry.get_string(RB.RhythmDBPropType.ARTIST)
            album = entry.get_string(RB.RhythmDBPropType.ALBUM)

            logger.info(f"Processing song: {title} by {artist} (album: {album})")

            # Extract album art from music file first
            album_art_path = self._extract_album_art(entry)

            if album_art_path and os.path.exists(album_art_path):
                # Generate cache key from album + artist
                cache_key = self._generate_cache_key(album, artist)

                # Check cache for this album art
                cached_palette = self.color_cache.get(cache_key)
                if cached_palette:
                    logger.info("Using cached palette")
                    self.theme_manager.apply_theme(cached_palette)
                    return
                logger.info(f"Extracting colors from: {album_art_path}")
                self.pending_extraction = True

                # Extract colors asynchronously
                # Capture cache_key in closure for callback
                def on_extraction_complete(palette: Optional[ColorPalette], key=cache_key):
                    self.pending_extraction = False

                    if palette:
                        # Cache the palette
                        self.color_cache.put(key, palette)

                        # Apply theme
                        self.theme_manager.apply_theme(palette)
                        logger.info("Theme applied from extracted colors")
                    else:
                        # Extraction failed, use default
                        logger.warning("Color extraction failed, using default theme")
                        self._apply_default_theme()

                extract_colors_async(album_art_path, on_extraction_complete)
            else:
                logger.info("No album art found, using default theme")
                self._apply_default_theme()

        except Exception as e:
            logger.error(f"Error processing song change: {e}", exc_info=True)
            self._apply_default_theme()

    def _generate_cache_key(self, album: str, artist: str) -> str:
        """
        Generate cache key from album and artist.

        Args:
            album: Album name
            artist: Artist name

        Returns:
            MD5 hash of album+artist
        """
        key_str = f"{album or 'unknown'}-{artist or 'unknown'}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _extract_album_art(self, entry: RB.RhythmDBEntry) -> Optional[str]:
        """
        Extract album art from music file's embedded metadata.

        Args:
            entry: RhythmDBEntry

        Returns:
            Path to extracted album art image, or None if not found
        """
        try:
            # Get the music file location
            location = entry.get_string(RB.RhythmDBPropType.LOCATION)
            if not location:
                return None

            file_path = urllib.parse.unquote(location.replace("file://", ""))
            if not os.path.exists(file_path):
                logger.debug(f"Music file not found: {file_path}")
                return None

            # First check for external album art files in the same directory
            dir_path = os.path.dirname(file_path)
            for cover_name in ["cover.jpg", "cover.png", "folder.jpg", "folder.png",
                               "album.jpg", "album.png", "front.jpg", "front.png"]:
                cover_path = os.path.join(dir_path, cover_name)
                if os.path.exists(cover_path):
                    logger.info(f"Found external cover art: {cover_path}")
                    return cover_path

            # Try to extract embedded album art
            try:
                from mutagen import File as MutagenFile
                from PIL import Image
                import io
            except ImportError:
                logger.debug("mutagen or PIL not available for embedded art extraction")
                return None

            audio = MutagenFile(file_path)
            if audio is None:
                return None

            image_data = None

            # FLAC files - check first since they have a specific pictures attribute
            if hasattr(audio, 'pictures') and audio.pictures:
                image_data = audio.pictures[0].data
                logger.debug("Extracted album art from FLAC pictures")

            # MP4/M4A files - check for 'covr' tag
            elif hasattr(audio, 'tags') and audio.tags and 'covr' in audio.tags:
                image_data = bytes(audio.tags['covr'][0])
                logger.debug("Extracted album art from MP4/M4A covr tag")

            # MP3 files with ID3 tags - check for APIC frames
            elif hasattr(audio, 'tags') and audio.tags:
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        image_data = audio.tags[key].data
                        logger.debug("Extracted album art from MP3 APIC tag")
                        break

            if image_data:
                # Validate and save to temp file
                try:
                    img = Image.open(io.BytesIO(image_data))
                    img.verify()

                    # Create temp file
                    temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='rhythmbox-dynamic-theme-')
                    os.close(temp_fd)

                    # Re-open and save
                    img = Image.open(io.BytesIO(image_data))
                    img = img.convert('RGB')
                    img.save(temp_path, 'JPEG', quality=90)

                    self.temp_art_files.append(temp_path)
                    logger.info(f"Extracted embedded album art to {temp_path}")
                    return temp_path

                except Exception as e:
                    logger.debug(f"Failed to process embedded image: {e}")
                    return None

            logger.debug("No album art found in music file")
            return None

        except Exception as e:
            logger.error(f"Error extracting album art: {e}", exc_info=True)
            return None

    def _apply_default_theme(self) -> None:
        """Apply default fallback theme when album art is missing."""
        try:
            # Create default palette from config
            def hex_to_rgb(hex_color: str):
                hex_color = hex_color.lstrip('#')
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

            default_palette = ColorPalette(
                primary=hex_to_rgb(self.config.default_primary),
                secondary=hex_to_rgb(self.config.default_secondary),
                background=hex_to_rgb(self.config.default_background),
                foreground=hex_to_rgb(self.config.default_foreground),
                accent=hex_to_rgb(self.config.default_accent),
                contrast_ratio_bg_fg=12.0,  # Default colors are pre-validated
                source_hash="default"
            )

            self.theme_manager.apply_theme(default_palette)
            logger.info("Default theme applied")

        except Exception as e:
            logger.error(f"Error applying default theme: {e}", exc_info=True)

    def apply_theme_to_current_song(self) -> None:
        """Apply theme to currently playing song (called on activation)."""
        try:
            if self.player:
                entry = self.player.get_playing_entry()
                if entry:
                    self.on_playing_song_changed(self.player, entry)
                else:
                    # No song playing, apply default theme
                    logger.info("No song playing on activation, applying default theme")
                    self._apply_default_theme()

        except Exception as e:
            logger.error(f"Error applying theme to current song: {e}", exc_info=True)

    def _cleanup_temp_files(self):
        """Clean up temporary album art files."""
        for temp_file in self.temp_art_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                logger.debug(f"Error cleaning up {temp_file}: {e}")
        self.temp_art_files.clear()

    def do_create_configure_widget(self):
        """
        Create and return the preferences dialog widget.

        This is called by Rhythmbox when the user clicks the Preferences
        button for this plugin.

        Returns:
            Gtk.Widget: The preferences configuration widget
        """
        try:
            # Initialize config if not already done (preferences can be accessed before activation)
            if self.config is None:
                self.config = PluginConfiguration()

            # Get the directory where the plugin is located
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file = os.path.join(plugin_dir, 'preferences.ui')

            # Load the UI file
            builder = Gtk.Builder()
            builder.add_from_file(ui_file)

            # Get the main container
            preferences_box = builder.get_object('preferences_box')

            # Get color buttons
            primary_button = builder.get_object('primary_color_button')
            secondary_button = builder.get_object('secondary_color_button')
            background_button = builder.get_object('background_color_button')
            foreground_button = builder.get_object('foreground_color_button')
            accent_button = builder.get_object('accent_color_button')

            # Get reset buttons and restart bar
            reset_primary_button = builder.get_object('reset_primary_button')
            reset_secondary_button = builder.get_object('reset_secondary_button')
            reset_background_button = builder.get_object('reset_background_button')
            reset_foreground_button = builder.get_object('reset_foreground_button')
            reset_accent_button = builder.get_object('reset_accent_button')
            restart_bar = builder.get_object('restart_bar')
            restart_app_button = builder.get_object('restart_app_button')

            # Helper function to convert hex to Gdk.RGBA
            def hex_to_rgba(hex_color):
                hex_color = hex_color.lstrip('#')
                r = int(hex_color[0:2], 16) / 255.0
                g = int(hex_color[2:4], 16) / 255.0
                b = int(hex_color[4:6], 16) / 255.0
                rgba = Gdk.RGBA()
                rgba.red = r
                rgba.green = g
                rgba.blue = b
                rgba.alpha = 1.0
                return rgba

            # Helper function to convert Gdk.RGBA to hex
            def rgba_to_hex(rgba):
                r = int(rgba.red * 255)
                g = int(rgba.green * 255)
                b = int(rgba.blue * 255)
                return f'#{r:02x}{g:02x}{b:02x}'

            # Set initial colors
            primary_button.set_rgba(hex_to_rgba(self.config.default_primary))
            secondary_button.set_rgba(hex_to_rgba(self.config.default_secondary))
            background_button.set_rgba(hex_to_rgba(self.config.default_background))
            foreground_button.set_rgba(hex_to_rgba(self.config.default_foreground))
            accent_button.set_rgba(hex_to_rgba(self.config.default_accent))

            # Connect color change handlers
            def on_primary_color_set(button):
                rgba = button.get_rgba()
                self.config.default_primary = rgba_to_hex(rgba)
                restart_bar.set_visible(True)
                logger.info(f"Primary color changed to: {self.config.default_primary}")

            def on_secondary_color_set(button):
                rgba = button.get_rgba()
                self.config.default_secondary = rgba_to_hex(rgba)
                restart_bar.set_visible(True)
                logger.info(f"Secondary color changed to: {self.config.default_secondary}")

            def on_background_color_set(button):
                rgba = button.get_rgba()
                self.config.default_background = rgba_to_hex(rgba)
                restart_bar.set_visible(True)
                logger.info(f"Background color changed to: {self.config.default_background}")

            def on_foreground_color_set(button):
                rgba = button.get_rgba()
                self.config.default_foreground = rgba_to_hex(rgba)
                restart_bar.set_visible(True)
                logger.info(f"Foreground color changed to: {self.config.default_foreground}")

            def on_accent_color_set(button):
                rgba = button.get_rgba()
                self.config.default_accent = rgba_to_hex(rgba)
                restart_bar.set_visible(True)
                logger.info(f"Accent color changed to: {self.config.default_accent}")

            primary_button.connect('color-set', on_primary_color_set)
            secondary_button.connect('color-set', on_secondary_color_set)
            background_button.connect('color-set', on_background_color_set)
            foreground_button.connect('color-set', on_foreground_color_set)
            accent_button.connect('color-set', on_accent_color_set)

            # Connect individual reset button handlers
            def on_reset_primary_clicked(button):
                default_color = '#9e0d43'
                self.config.default_primary = default_color
                primary_button.set_rgba(hex_to_rgba(default_color))
                restart_bar.set_visible(True)
                logger.info(f"Primary color reset to default: {default_color}")

            def on_reset_secondary_clicked(button):
                default_color = '#305b82'
                self.config.default_secondary = default_color
                secondary_button.set_rgba(hex_to_rgba(default_color))
                restart_bar.set_visible(True)
                logger.info(f"Secondary color reset to default: {default_color}")

            def on_reset_background_clicked(button):
                default_color = '#04040a'
                self.config.default_background = default_color
                background_button.set_rgba(hex_to_rgba(default_color))
                restart_bar.set_visible(True)
                logger.info(f"Background color reset to default: {default_color}")

            def on_reset_foreground_clicked(button):
                default_color = '#f0f0f0'
                self.config.default_foreground = default_color
                foreground_button.set_rgba(hex_to_rgba(default_color))
                restart_bar.set_visible(True)
                logger.info(f"Foreground color reset to default: {default_color}")

            def on_reset_accent_clicked(button):
                default_color = '#9e0d43'
                self.config.default_accent = default_color
                accent_button.set_rgba(hex_to_rgba(default_color))
                restart_bar.set_visible(True)
                logger.info(f"Accent color reset to default: {default_color}")

            reset_primary_button.connect('clicked', on_reset_primary_clicked)
            reset_secondary_button.connect('clicked', on_reset_secondary_clicked)
            reset_background_button.connect('clicked', on_reset_background_clicked)
            reset_foreground_button.connect('clicked', on_reset_foreground_clicked)
            reset_accent_button.connect('clicked', on_reset_accent_clicked)

            # Connect restart button handler
            def on_restart_clicked(button):
                import shutil
                import sys
                try:
                    # Find rhythmbox executable path
                    exepath = shutil.which('rhythmbox')
                    if exepath:
                        logger.info("Restarting Rhythmbox")
                        # Replace current process with new Rhythmbox instance
                        os.execl(exepath, exepath, *sys.argv)
                    else:
                        logger.error("Could not find rhythmbox executable")
                except Exception as e:
                    logger.error(f"Error restarting Rhythmbox: {e}", exc_info=True)

            restart_app_button.connect('clicked', on_restart_clicked)

            logger.info("Preferences widget created successfully")
            return preferences_box

        except Exception as e:
            logger.error(f"Error creating preferences widget: {e}", exc_info=True)
            error_label = Gtk.Label(label=f"Error loading preferences: {e}")
            error_label.show()
            return error_label
