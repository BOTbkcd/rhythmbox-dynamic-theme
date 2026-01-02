import logging
from collections import OrderedDict
from typing import Optional
from color_extractor import ColorPalette

logger = logging.getLogger('rhythm-hue.color-cache')

class ColorCache:
    """
    LRU cache for storing extracted color palettes to improve performance
    """

    def __init__(self, max_size: int = 128):
        """
        Initialize cache with maximum size.
        """
        if max_size < 1:
            raise ValueError("max_size must be at least 1")

        self.max_size = max_size
        self.cache = OrderedDict()  # Maintains insertion order for LRU
        self.total_requests = 0
        self.total_hits = 0

        logger.info(f"ColorCache initialized with max_size={max_size}")

    def get(self, cache_key: str) -> Optional[ColorPalette]:
        """
        Retrieve cached palette.

        Args:
            cache_key: MD5 hash of album+artist

        Returns:
            ColorPalette if cached, None otherwise

        Side Effects:
            Updates LRU access order
        """
        self.total_requests += 1

        if cache_key in self.cache:
            self.total_hits += 1
            # Move to end (most recently used)
            self.cache.move_to_end(cache_key)
            logger.debug(f"Cache HIT for key {cache_key[:8]}...")
            return self.cache[cache_key]

        logger.debug(f"Cache MISS for key {cache_key[:8]}...")
        return None

    def put(self, cache_key: str, palette: ColorPalette) -> None:
        """
        Store palette in cache.

        Args:
            cache_key: hash of album+artist
            palette: ColorPalette to cache

        Behavior:
            If cache is full, evicts least recently used entry
        """
        if cache_key in self.cache:
            # Update existing entry
            self.cache.move_to_end(cache_key)
            self.cache[cache_key] = palette
            logger.debug(f"Cache UPDATE for key {cache_key[:8]}...")
        else:
            # Add new entry
            if len(self.cache) >= self.max_size:
                # Evict least recently used
                evicted_key = next(iter(self.cache))
                del self.cache[evicted_key]
                logger.debug(f"Cache EVICT key {evicted_key[:8]}...")

            self.cache[cache_key] = palette
            logger.debug(f"Cache PUT key {cache_key[:8]}... (size={len(self.cache)})")

    def invalidate(self, cache_key: str) -> None:
        """
        Remove specific entry from cache.

        Args:
            cache_key: MD5 hash of album+artist
        """
        if cache_key in self.cache:
            del self.cache[cache_key]
            logger.debug(f"Cache INVALIDATE key {cache_key[:8]}...")

    def clear(self) -> None:
        """Empty entire cache."""
        self.cache.clear()
        logger.info("Cache CLEARED")

    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics:
            - size: Current number of cached entries
            - max_size: Maximum capacity
            - hit_rate: Cache hit percentage (0.0-1.0)
            - total_requests: Total cache lookups
            - total_hits: Successful cache hits
        """
        hit_rate = self.total_hits / self.total_requests if self.total_requests > 0 else 0.0

        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_rate': hit_rate,
            'total_requests': self.total_requests,
            'total_hits': self.total_hits
        }

    def __len__(self) -> int:
        """Return current cache size."""
        return len(self.cache)

    def __contains__(self, cache_key: str) -> bool:
        """Check if key is in cache."""
        return cache_key in self.cache
