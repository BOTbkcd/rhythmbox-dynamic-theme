"""
This module handles extracting dominant colors from album art images and ensuring WCAG AA contrast compliance
"""

import hashlib
import logging
import colorsys
from dataclasses import dataclass
from typing import Tuple, Optional, Callable
from PIL import Image
from gi.repository import GObject

logger = logging.getLogger('rhythm-hue.color-extractor')

# Type alias for RGB colors
RGB = Tuple[int, int, int]

@dataclass
class ColorPalette:
    """
    Represents an extracted color palette from album art.

    All RGB values must be in range [0, 255].
    Contrast ratio between background and foreground must meet WCAG AA (>= 4.5).
    """
    primary: RGB           # Most vibrant color for accents
    secondary: RGB         # Secondary accent color
    background: RGB        # Background color (usually darkest)
    foreground: RGB        # Text/foreground color (usually lightest)
    accent: RGB            # Additional accent for highlights
    contrast_ratio_bg_fg: float  # WCAG contrast ratio
    source_hash: str       # Cache key for this palette

    def __post_init__(self):
        """Validate RGB values and contrast ratio."""
        for color_name in ['primary', 'secondary', 'background', 'foreground', 'accent']:
            color = getattr(self, color_name)
            if not all(0 <= c <= 255 for c in color):
                raise ValueError(f"{color_name} RGB values must be in range [0, 255]")

        if self.contrast_ratio_bg_fg < 4.5:
            logger.warning(f"Contrast ratio {self.contrast_ratio_bg_fg:.2f} below WCAG AA minimum (4.5)")


def luminance(r: int, g: int, b: int) -> float:
    """
    Calculate relative luminance per WCAG standards.

    Args:
        r, g, b: RGB color components (0-255)

    Returns:
        Relative luminance (0.0 - 1.0)
    """
    def adjust(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)


def contrast_ratio(rgb1: RGB, rgb2: RGB) -> float:
    """
    Calculate WCAG contrast ratio between two colors.

    Args:
        rgb1: First RGB color
        rgb2: Second RGB color

    Returns:
        Contrast ratio (1.0 - 21.0)
    """
    l1 = luminance(*rgb1)
    l2 = luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def adjust_for_contrast(fg: RGB, bg: RGB, min_ratio: float = 4.5) -> Tuple[RGB, RGB]:
    """
    Adjust foreground/background colors to meet minimum contrast ratio.

    Preserves hue and saturation as much as possible while adjusting lightness.

    Args:
        fg: Foreground color (text)
        bg: Background color
        min_ratio: Minimum WCAG contrast ratio (default 4.5 for AA)

    Returns:
        Tuple of (adjusted_fg, adjusted_bg)
    """
    current_ratio = contrast_ratio(fg, bg)

    if current_ratio >= min_ratio:
        return fg, bg

    logger.debug(f"Adjusting contrast from {current_ratio:.2f} to meet {min_ratio}")

    # Convert to HSV for easier lightness adjustment
    fg_h, fg_s, fg_v = colorsys.rgb_to_hsv(fg[0]/255, fg[1]/255, fg[2]/255)
    bg_h, bg_s, bg_v = colorsys.rgb_to_hsv(bg[0]/255, bg[1]/255, bg[2]/255)

    # Determine which is lighter
    if fg_v > bg_v:
        # Foreground is lighter - lighten it more
        for i in range(20):
            fg_v = min(1.0, fg_v + 0.05)
            adjusted_fg_rgb = colorsys.hsv_to_rgb(fg_h, fg_s, fg_v)
            adjusted_fg = tuple(int(c * 255) for c in adjusted_fg_rgb)

            if contrast_ratio(adjusted_fg, bg) >= min_ratio:
                return adjusted_fg, bg
    else:
        # Background is lighter - lighten fg or darken bg
        for i in range(20):
            fg_v = min(1.0, fg_v + 0.05)
            adjusted_fg_rgb = colorsys.hsv_to_rgb(fg_h, fg_s, fg_v)
            adjusted_fg = tuple(int(c * 255) for c in adjusted_fg_rgb)

            if contrast_ratio(adjusted_fg, bg) >= min_ratio:
                return adjusted_fg, bg

        # If lightening fg didn't work, try darkening bg
        for i in range(20):
            bg_v = max(0.0, bg_v - 0.05)
            adjusted_bg_rgb = colorsys.hsv_to_rgb(bg_h, bg_s, bg_v)
            adjusted_bg = tuple(int(c * 255) for c in adjusted_bg_rgb)

            if contrast_ratio(fg, adjusted_bg) >= min_ratio:
                return fg, adjusted_bg

    # Fallback: use appropriate default foreground based on background lightness
    logger.warning(f"Could not achieve contrast ratio {min_ratio}, using default foreground")

    # If background is light (lightness > 0.5), use dark foreground
    # If background is dark (lightness <= 0.5), use light foreground
    if bg_v > 0.5:
        # Light background - use dark charcoal foreground
        default_fg = (40, 40, 40)
        logger.debug(f"Light background detected, using dark foreground {default_fg}")
    else:
        # Dark background - use off-white foreground
        default_fg = (245, 245, 245)
        logger.debug(f"Dark background detected, using light foreground {default_fg}")

    final_ratio = contrast_ratio(default_fg, bg)
    logger.debug(f"Fallback contrast ratio: {final_ratio:.2f}")

    return default_fg, bg


def extract_dominant_colors(image_path: str, num_colors: int = 15) -> list[RGB]:
    """
    Extract dominant colors from an image using quantization.

    Args:
        image_path: Absolute path to image file
        num_colors: Number of dominant colors to extract (default 15)

    Returns:
        List of RGB tuples representing dominant colors
    """
    # Load and resize image for performance
    img = Image.open(image_path)
    img = img.resize((150, 150))
    img = img.convert('RGB')

    # Extract dominant colors using quantization
    palette_img = img.quantize(colors=num_colors)
    palette = palette_img.getpalette()

    # Extract RGB colors
    all_colors = []
    for i in range(num_colors):
        r = palette[i * 3]
        g = palette[i * 3 + 1]
        b = palette[i * 3 + 2]
        all_colors.append((r, g, b))

    return all_colors


def filter_distinct_colors(colors: list[RGB], max_count: int = 8, min_distance: float = 30) -> list[RGB]:
    """
    Filter a list of colors to keep only visually distinct ones.

    Args:
        colors: List of RGB color tuples to filter
        max_count: Maximum number of distinct colors to return (default 8)
        min_distance: Minimum euclidean distance between colors to be considered distinct (default 30)

    Returns:
        List of distinct RGB colors, up to max_count
    """
    if not colors:
        return []

    def color_distance(c1: RGB, c2: RGB) -> float:
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

    # Start with first color
    distinct_colors = [colors[0]]

    # Add colors that are sufficiently different from existing ones
    for color in colors[1:]:
        if all(color_distance(color, existing) > min_distance for existing in distinct_colors):
            distinct_colors.append(color)
        if len(distinct_colors) >= max_count:
            break

    # If we don't have sufficient distinct colors, pad with remaining colors
    for color in colors:
        if color not in distinct_colors:
            distinct_colors.append(color)
        if len(distinct_colors) >= max_count:
            break

    return distinct_colors[:max_count]


def get_saturation(rgb: RGB) -> float:
    """
    Calculate the saturation value of an RGB color.

    Args:
        rgb: RGB color tuple

    Returns:
        Saturation value (0.0 - 1.0)
    """
    _, s, _ = colorsys.rgb_to_hsv(rgb[0]/255, rgb[1]/255, rgb[2]/255)
    return s


def get_lightness(rgb: RGB) -> float:
    """
    Calculate the lightness (value) of an RGB color.

    Args:
        rgb: RGB color tuple

    Returns:
        Lightness value (0.0 - 1.0)
    """
    _, _, v = colorsys.rgb_to_hsv(rgb[0]/255, rgb[1]/255, rgb[2]/255)
    return v


def is_vibrant_and_visible(rgb: RGB) -> bool:
    """
    Check if a color is both vibrant (saturated) and visible (not too dark).

    Args:
        rgb: RGB color tuple

    Returns:
        True if color has both sufficient saturation and lightness
    """
    _, s, v = colorsys.rgb_to_hsv(rgb[0]/255, rgb[1]/255, rgb[2]/255)
    return s > 0.2 and v > 0.2  # Must have both saturation and lightness


def extract_colors_sync(image_path: str) -> Optional[ColorPalette]:
    """
    Synchronously extract color palette from album art.

    Args:
        image_path: Absolute path to album art image file

    Returns:
        ColorPalette or None on failure
    """
    try:
        colors = extract_dominant_colors(image_path, num_colors=15)
        # logger.info(f"Initial extracted colors (by frequency): {colors}")

        # Before filtering, identify the absolute darkest and lightest colors
        # These are critical for background/foreground and should be preserved
        darkest = min(colors, key=get_lightness)
        lightest = max(colors, key=get_lightness)

        colors = filter_distinct_colors(colors, max_count=8, min_distance=30)

        # Ensure darkest and lightest are in the filtered list
        if darkest not in colors:
            colors.insert(0, darkest)
        if lightest not in colors:
            colors.append(lightest)

        # logger.info(f"After filtering to distinct colors: {colors}")

        # Sort by saturation to find vibrant colors
        colors_by_saturation = sorted(colors, key=get_saturation, reverse=True)
        # logger.info(f"Colors by saturation (high to low): {[(c, f'{get_saturation(c):.3f}') for c in colors_by_saturation]}")

        # Sort by lightness to find darkest/lightest
        colors_by_lightness = sorted(colors, key=get_lightness)
        # logger.info(f"Colors by lightness (low to high): {[(c, f'{get_lightness(c):.3f}') for c in colors_by_lightness]}")

        background = colors_by_lightness[0]  # Darkest (guaranteed to be true darkest now)
        foreground = colors_by_lightness[-1]  # Lightest (guaranteed to be true lightest now)
        
        # Ensure contrast compliance
        foreground, background = adjust_for_contrast(foreground, background, min_ratio=4.5)

        # Primary should be vibrant AND visible (not too dark)
        # Filter out colors that are too dark (lightness < 0.2) as they appear black even if they have high saturation
        vibrant_colors = [c for c in colors_by_saturation if is_vibrant_and_visible(c)]
        
        # Pick primary from vibrant visible colors, avoiding background
        if vibrant_colors:
            primary = vibrant_colors[0]
            if primary == background and len(vibrant_colors) > 1:
                primary = vibrant_colors[1]
        else:
            # Fallback to most saturated if no vibrant colors found
            primary = colors_by_saturation[0]
            if primary == background and len(colors_by_saturation) > 1:
                primary = colors_by_saturation[1]

        # Secondary and accent should also be vibrant and distinct
        secondary = vibrant_colors[1] if len(vibrant_colors) > 1 else primary
        if secondary == background and len(vibrant_colors) > 2:
                secondary = vibrant_colors[2]

        accent = vibrant_colors[2] if len(vibrant_colors) > 2 else primary
        if accent == background and len(vibrant_colors) > 3:
            accent = vibrant_colors[3]
        
        # Calculate contrast ratio
        ratio = contrast_ratio(foreground, background)

        # Generate cache key
        cache_key = hashlib.md5(image_path.encode()).hexdigest()

        # logger.info({ 'primary': primary, 'secondary': secondary, 'background': background, 'foreground': foreground, 'accent': accent })
        return ColorPalette(
            primary=primary,
            secondary=secondary,
            background=background,
            foreground=foreground,
            accent=accent,
            contrast_ratio_bg_fg=ratio,
            source_hash=cache_key
        )

    except FileNotFoundError:
        logger.error(f"Image file not found: {image_path}")
        return None
    except Exception as e:
        logger.error(f"Error extracting colors from {image_path}: {e}", exc_info=True)
        return None


def extract_colors_async(image_path: str, callback: Callable[[Optional[ColorPalette]], None]) -> None:
    """
    Asynchronously extract color palette from album art.

    Runs extraction in background and calls callback with result on main thread.

    Args:
        image_path: Absolute path to album art image file
        callback: Function to call with extracted ColorPalette (or None on failure)
    """
    def run_extraction():
        """Extract colors in background."""
        palette = extract_colors_sync(image_path)

        # Call callback on main thread
        GObject.idle_add(lambda: callback(palette) or False)

    # Run in background thread via GObject
    import threading
    thread = threading.Thread(target=run_extraction, daemon=True)
    thread.start()
