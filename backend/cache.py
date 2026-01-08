"""
Redis Cache Wrapper Module.

Provides caching functionality for the Beans&Co backend with:
- Automatic tenant-scoped cache keys
- JSON serialization/deserialization
- TTL management
- Graceful fallback when Redis is unavailable
- Pattern-based cache invalidation
"""
import os
import json
import redis
from typing import Optional, Any
from functools import wraps
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis configuration from environment
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Default TTL values (in seconds)
TTL_PRODUCTS = 300  # 5 minutes
TTL_STOCK = 60      # 1 minute
TTL_STATS = 120     # 2 minutes
TTL_SALES = 120     # 2 minutes

# Global Redis client
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get or create Redis client.
    
    Returns:
        Redis client or None if Redis is disabled or unavailable
    """
    global _redis_client
    
    if not REDIS_ENABLED:
        return None
    
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"[CACHE] Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.warning(f"[CACHE] Redis unavailable: {e}. Caching disabled.")
            _redis_client = None
    
    return _redis_client


def get_tenant_key(phone: str, resource: str, identifier: str = "") -> str:
    """
    Generate a cache key for a tenant resource.
    
    Args:
        phone: Tenant phone number
        resource: Resource type (e.g., 'products', 'stock', 'stats')
        identifier: Optional specific identifier (e.g., product ID, 'all', 'active')
    
    Returns:
        Cache key string
    
    Example:
        get_tenant_key("+541153695627", "products", "all")
        -> "tenant:+541153695627:products:all"
    """
    if identifier:
        return f"tenant:{phone}:{resource}:{identifier}"
    return f"tenant:{phone}:{resource}"


def get_cache(key: str) -> Optional[Any]:
    """
    Get value from cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value (deserialized from JSON) or None if not found
    """
    client = get_redis_client()
    if not client:
        return None
    
    try:
        value = client.get(key)
        if value:
            logger.debug(f"[CACHE] HIT: {key}")
            return json.loads(value)
        logger.debug(f"[CACHE] MISS: {key}")
        return None
    except Exception as e:
        logger.error(f"[CACHE] Error getting key {key}: {e}")
        return None


def set_cache(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set value in cache.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time to live in seconds (default: 300)
    
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        serialized = json.dumps(value)
        client.setex(key, ttl, serialized)
        logger.debug(f"[CACHE] SET: {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.error(f"[CACHE] Error setting key {key}: {e}")
        return False


def delete_cache(key: str) -> bool:
    """
    Delete a specific cache key.
    
    Args:
        key: Cache key to delete
    
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.delete(key)
        logger.debug(f"[CACHE] DELETE: {key}")
        return True
    except Exception as e:
        logger.error(f"[CACHE] Error deleting key {key}: {e}")
        return False


def delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    
    Args:
        pattern: Pattern to match (e.g., "tenant:+541153695627:products:*")
    
    Returns:
        Number of keys deleted
    """
    client = get_redis_client()
    if not client:
        return 0
    
    try:
        keys = client.keys(pattern)
        if keys:
            deleted = client.delete(*keys)
            logger.debug(f"[CACHE] DELETE PATTERN: {pattern} ({deleted} keys)")
            return deleted
        return 0
    except Exception as e:
        logger.error(f"[CACHE] Error deleting pattern {pattern}: {e}")
        return 0


def invalidate_tenant_cache(phone: str, resource: str = "*"):
    """
    Invalidate all cache for a tenant resource.
    
    Args:
        phone: Tenant phone number
        resource: Resource type or "*" for all resources
    
    Example:
        invalidate_tenant_cache("+541153695627", "products")
        invalidate_tenant_cache("+541153695627")  # All resources
    """
    pattern = get_tenant_key(phone, resource, "*")
    deleted = delete_pattern(pattern)
    if deleted > 0:
        logger.info(f"[CACHE] Invalidated {deleted} keys for tenant {phone}/{resource}")


def cached(ttl: int = 300, key_func=None):
    """
    Decorator to cache function results.
    
    Args:
        ttl: Time to live in seconds
        key_func: Function to generate cache key from function args
                 If None, uses function name and args
    
    Example:
        @cached(ttl=300, key_func=lambda phone, active: f"tenant:{phone}:products:{'active' if active else 'all'}")
        def get_products(phone: str, active: bool = True):
            # ... expensive database query
            return products
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_value = get_cache(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            set_cache(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


# Convenience functions for common cache operations

def cache_products(phone: str, products: list, active_only: bool = False) -> bool:
    """Cache products list."""
    identifier = "active" if active_only else "all"
    key = get_tenant_key(phone, "products", identifier)
    return set_cache(key, products, TTL_PRODUCTS)


def get_cached_products(phone: str, active_only: bool = False) -> Optional[list]:
    """Get cached products list."""
    identifier = "active" if active_only else "all"
    key = get_tenant_key(phone, "products", identifier)
    return get_cache(key)


def cache_product(phone: str, product_id: int, product: dict) -> bool:
    """Cache a single product."""
    key = get_tenant_key(phone, "product", str(product_id))
    return set_cache(key, product, TTL_PRODUCTS)


def get_cached_product(phone: str, product_id: int) -> Optional[dict]:
    """Get cached product."""
    key = get_tenant_key(phone, "product", str(product_id))
    return get_cache(key)


def cache_stock(phone: str, stock: list) -> bool:
    """Cache stock data."""
    key = get_tenant_key(phone, "stock", "current")
    return set_cache(key, stock, TTL_STOCK)


def get_cached_stock(phone: str) -> Optional[list]:
    """Get cached stock data."""
    key = get_tenant_key(phone, "stock", "current")
    return get_cache(key)


def cache_stats(phone: str, stats: dict) -> bool:
    """Cache statistics."""
    key = get_tenant_key(phone, "stats", "summary")
    return set_cache(key, stats, TTL_STATS)


def get_cached_stats(phone: str) -> Optional[dict]:
    """Get cached statistics."""
    key = get_tenant_key(phone, "stats", "summary")
    return get_cache(key)


# Cache invalidation helpers

def invalidate_products(phone: str):
    """Invalidate all product caches for a tenant."""
    invalidate_tenant_cache(phone, "products")
    invalidate_tenant_cache(phone, "product")


def invalidate_stock(phone: str):
    """Invalidate stock cache for a tenant."""
    invalidate_tenant_cache(phone, "stock")


def invalidate_stats(phone: str):
    """Invalidate statistics cache for a tenant."""
    invalidate_tenant_cache(phone, "stats")


def invalidate_all(phone: str):
    """Invalidate all caches for a tenant."""
    invalidate_tenant_cache(phone)
