# DNS Server

A high-performance, configurable DNS server with real-time web interface and advanced caching capabilities.

## Quick Start

### Method 1: Using Management Script (Recommended)

1. **Setup Environment**:
```bash
# Install Python 3.8 or higher
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Start the Server**:
```bash
./scripts/dns-server.sh start
```

3. **Check Status**:
```bash
./scripts/dns-server.sh status
```

4. **View Logs**:
```bash
./scripts/dns-server.sh logs
```

5. **Stop the Server**:
```bash
./scripts/dns-server.sh stop
```

### Method 2: Using Docker Compose

1. **Start with Docker Compose**:
```bash
docker-compose up -d
```

2. **Check Status**:
```bash
docker-compose ps
docker-compose logs dns-server
```

3. **Stop the Server**:
```bash
docker-compose down
```

## Management Scripts

### Bash Script Commands

The `scripts/dns-server.sh` script provides easy server management:

```bash
# Server operations
./scripts/dns-server.sh start           # Start the DNS server
./scripts/dns-server.sh stop            # Stop the DNS server
./scripts/dns-server.sh restart         # Restart the DNS server
./scripts/dns-server.sh status          # Show detailed server status

# Log management
./scripts/dns-server.sh logs            # Show last 50 lines of logs
./scripts/dns-server.sh logs 100        # Show last 100 lines of logs
./scripts/dns-server.sh logs follow     # Follow logs in real-time

# Help
./scripts/dns-server.sh                 # Show usage information
```

### Docker Compose Commands

For containerized deployment:

```bash
# Basic operations
docker-compose up -d                    # Start in background
docker-compose down                     # Stop and remove containers
docker-compose restart dns-server       # Restart DNS server service
docker-compose logs -f dns-server       # Follow logs in real-time

# Management
docker-compose exec dns-server bash     # Shell into container
docker-compose ps                       # Show container status
docker-compose pull && docker-compose up -d  # Update and restart
```

## Server Access

When running, the DNS server is accessible at:
- **DNS queries**: `127.0.0.1:9953` (UDP/TCP)
- **Web interface**: `http://127.0.0.1:9980`

## Configuration

### Custom Configuration

Edit `config/default.yaml` to customize server settings:

- **DNS Port**: Change `server.dns_port` (default: 9953)
- **Web Port**: Change `server.web_port` (default: 9980)
- **Bind Address**: Change `server.bind_address`
- **Upstream Servers**: Modify `upstream_servers` list
- **Cache Size**: Adjust `cache.max_size_mb`
- **Web Interface**: Enable/disable with `web.enabled`

After editing configuration:
```bash
# With management script
./scripts/dns-server.sh restart

# With Docker Compose
docker-compose restart dns-server
```

## Testing DNS Queries

Once the server is running, test it with `dig` or `nslookup`:

```bash
# Using dig
dig @127.0.0.1 -p 9953 google.com

# Using nslookup
nslookup google.com 127.0.0.1
```

## Advanced Usage

### Manual Server Start (Development)

For development or debugging, start the server manually:

```bash
# Activate virtual environment
source venv/bin/activate

# Start with default config
python src/dns_server/main.py

# Start with custom config
python src/dns_server/main.py --config /path/to/config.yaml

# Health check
python src/dns_server/main.py --health-check

# Performance statistics
python src/dns_server/main.py --performance-stats
```

### Performance Testing

Run the included performance test:
```bash
python test_performance.py
```

### Docker Development

Build and run with custom settings:
```bash
# Build image
docker build -t dns-server .

# Run with custom ports
docker run -p 9953:9953/udp -p 9953:9953/tcp -p 9980:9980 dns-server

# Run with custom config volume
docker run -v $(pwd)/config:/app/config dns-server
```

## Web Interface

Access the comprehensive web interface at `http://127.0.0.1:9980` for:

### Real-Time Monitoring
- Live DNS query feed with real-time updates via WebSocket
- Server status and uptime monitoring
- Connection status indicators
- Automatic refresh with manual refresh option

### Performance Analytics
- **Interactive Charts**: Query type distribution, cache hit/miss ratios, response time trends
- **DNS Statistics**: Total queries, UDP/TCP breakdown, error counts, queries per second
- **Cache Performance**: Hit ratios, memory usage, entry counts
- **System Metrics**: Memory usage, CPU statistics, connection counts

### Cache Management
- **Flush Operations**: Remove expired cache entries
- **Clear Cache**: Remove all cached entries with confirmation
- **Domain-Specific Flush**: Target specific domains for cache removal
- **Real-time Cache Statistics**: Current size, hit ratios, memory usage

### Query Analysis
- **Searchable Query History**: Filter by domain, IP, query type, or response code
- **Detailed Query Information**: Timestamps, client IPs, response times, cache status
- **Auto-scroll**: Automatically follow new queries as they arrive
- **Export Capability**: Download query data for analysis

### User Experience Features
- **Dark/Light Theme**: Toggle between themes with persistent preference
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Toast Notifications**: Real-time feedback for actions and events
- **Keyboard Navigation**: Full keyboard accessibility support

### API Access
The web interface also exposes REST API endpoints:
- `GET /api/status` - Server status and comprehensive statistics
- `GET /api/cache/stats` - Detailed cache performance metrics
- `POST /api/cache/flush` - Flush cache operations
- `GET /api/logs` - Query log history with filtering
- `GET /metrics` - Prometheus-compatible metrics

## Features

- **High Performance**: Optimized with uvloop and connection pooling
- **Advanced Caching**: Intelligent DNS response caching with TTL management
- **Real-Time Web Interface**: Modern dashboard with live updates and analytics
- **Security**: Rate limiting, network filtering, and access controls
- **Comprehensive Monitoring**: Built-in health checks, performance metrics, and alerting
- **Flexible Configuration**: Configurable upstream servers, resolution modes, and all parameters
- **API Integration**: REST API and WebSocket support for custom integrations
- **Production Ready**: Structured logging, graceful shutdown, and error handling
- **Easy Management**: Simple scripts and Docker support for deployment

## Common Use Cases

### Development DNS Server
Use as a local DNS server for development with custom configurations and real-time monitoring.

### DNS Proxy with Analytics
Forward DNS queries to multiple upstream servers with intelligent caching and comprehensive analytics.

### Performance Testing and Monitoring
Benchmark DNS resolution performance with built-in monitoring tools and real-time dashboards.

### Network Troubleshooting
Monitor DNS traffic patterns, identify slow queries, and analyze cache effectiveness.

## Troubleshooting

### Script Issues
- **Permission denied**: Run `chmod +x scripts/dns-server.sh`
- **Python not found**: Ensure Python 3.8+ is installed and in PATH
- **Virtual environment missing**: Run setup commands in Quick Start

### Docker Issues
- **Port conflicts**: Check if ports 9953 or 9980 are already in use
- **Permission denied**: Ensure Docker daemon is running and user has permissions
- **Build failures**: Check Dockerfile and ensure all files are present

### Web Interface Not Loading
- Check that the web port (default 9980) is not in use by another application
- Verify the web interface is enabled in configuration (`web.enabled: true`)
- Check firewall settings if accessing from another machine

### DNS Queries Not Working
- Ensure the DNS port (default 9953) is accessible
- Check upstream server connectivity
- Verify network configuration and routing

### Performance Issues
- Monitor cache hit ratios in the web interface
- Check system resource usage
- Review upstream server response times
- Consider adjusting cache size and TTL settings
