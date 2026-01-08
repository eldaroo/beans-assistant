# Redis Cache Integration - Quick Start

## Setup

### 1. Install Redis

**Option A: Using Docker (Recommended)**
```bash
docker-compose -f docker-compose.redis.yml up -d
```

**Option B: Install locally**
- Windows: Download from https://github.com/microsoftarchive/redis/releases
- Linux: `sudo apt-get install redis-server`
- Mac: `brew install redis`

### 2. Install Python Dependencies

```bash
pip install redis>=5.0.0
```

### 3. Configure Environment

Add to your `.env` file:
```bash
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

## Usage

The cache is automatically used in the following endpoints:

### Products
- `GET /api/tenants/{phone}/products` - Cached for 5 minutes
- `GET /api/tenants/{phone}/products/{id}` - Cached for 5 minutes
- Cache invalidated on: create, update, delete

### Stock
- `GET /api/tenants/{phone}/stock` - Cached for 1 minute
- Cache invalidated on: add stock, adjust stock, register sale

### Statistics
- Tenant stats in home page - Cached for 2 minutes
- Cache invalidated on: sales, expenses

## Testing

### 1. Verify Redis is Running

```bash
# Using Docker
docker ps | findstr redis

# Test connection
python -c "import redis; r = redis.Redis(host='localhost', port=6379); print('Redis OK' if r.ping() else 'Redis FAIL')"
```

### 2. Test Cache Performance

```powershell
# First request (cache miss - slower)
Measure-Command { Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products" }

# Second request (cache hit - faster)
Measure-Command { Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products" }
```

### 3. Test Cache Invalidation

```powershell
# Get products (cache miss)
$products = Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products"

# Get again (cache hit - fast)
$products = Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products"

# Create a product (invalidates cache)
$newProduct = @{
    sku = "TEST-001"
    name = "Test Product"
    unit_cost_cents = 1000
    unit_price_cents = 2000
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products" -Method POST -Body $newProduct -ContentType "application/json"

# Get products again (cache miss - will query DB)
$products = Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/+541153695627/products"
```

## Monitoring

### Check Cache Keys

```bash
# Connect to Redis CLI
docker exec -it beansco-redis redis-cli

# List all keys
KEYS *

# List keys for specific tenant
KEYS tenant:+541153695627:*

# Get cache value
GET "tenant:+541153695627:products:active"

# Check TTL
TTL "tenant:+541153695627:products:active"

# Clear all cache
FLUSHDB
```

### Cache Statistics

```bash
# In Redis CLI
INFO stats
```

## Disabling Cache

To disable Redis caching without removing the code:

```bash
# In .env
REDIS_ENABLED=false
```

The API will continue to work normally, just without caching.

## Troubleshooting

**Cache not working**:
- Check Redis is running: `docker ps` or `redis-cli ping`
- Check `.env` has `REDIS_ENABLED=true`
- Check logs for connection errors

**Stale data**:
- Cache should auto-invalidate on writes
- Manual clear: `docker exec -it beansco-redis redis-cli FLUSHDB`

**Performance not improving**:
- Check cache hit rate in logs
- Verify TTL values are appropriate
- Monitor Redis memory usage
