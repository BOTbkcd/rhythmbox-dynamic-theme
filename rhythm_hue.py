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
from gi.repository import GObject, Peas, RB
from color_extractor import ColorPalette, extract_colors_async, extract_colors_sync
from theme_manager import ThemeManager
from color_cache import ColorCache
from config import PluginConfiguration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('rhythmbox-dynamic-theme')


class RhythmHuePlugin(GObject.Object, Peas.Activatable):
    """
    Rhythmbox plugin that dynamically themes UI based on album art colors.

    Implements the Peas.Activatable interface for plugin lifecycle management.
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
