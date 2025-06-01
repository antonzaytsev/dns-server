# DNS Server

A high-performance, configurable DNS server with real-time web interface and advanced caching capabilities.

## Quick Start

### Installation

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Basic Usage

Start the DNS server with default settings:
```bash
python src/dns_server/main.py
```

The server will start on:
- **DNS queries**: `127.0.0.1:5353`
- **Web interface**: `http://127.0.0.1:8080`

## Configuration

### Custom Configuration

Use a custom configuration file:
```bash
python src/dns_server/main.py --config /path/to/your/config.yaml
```

### Default Configuration

The server uses `config/default.yaml` by default. Key settings you can modify:

- **DNS Port**: Change `server.dns_port` (default: 5353)
- **Web Port**: Change `server.web_port` (default: 8080)
- **Upstream Servers**: Modify `upstream_servers` list
- **Cache Size**: Adjust `cache.max_size_mb`
- **Bind Address**: Change `server.bind_address`
- **Web Interface**: Enable/disable with `web.enabled`

## Command Examples

### Start with Custom Port
```bash
# Edit config/default.yaml to change dns_port to 5353
python src/dns_server/main.py --config config/default.yaml
```

### Health Check
```bash
python src/dns_server/main.py --health-check
```

### Performance Statistics
```bash
python src/dns_server/main.py --performance-stats
```

### Testing DNS Queries

Once the server is running, test it with `dig` or `nslookup`:

```bash
# Using dig
dig @127.0.0.1 -p 5353 google.com

# Using nslookup
nslookup google.com 127.0.0.1
```

## Web Interface

Access the comprehensive web interface at `http://127.0.0.1:8080` for:

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

## Performance Testing

Run the included performance test:
```bash
python test_performance.py
```

## Features

- **High Performance**: Optimized with uvloop and connection pooling
- **Advanced Caching**: Intelligent DNS response caching with TTL management
- **Real-Time Web Interface**: Modern dashboard with live updates and analytics
- **Security**: Rate limiting, network filtering, and access controls
- **Comprehensive Monitoring**: Built-in health checks, performance metrics, and alerting
- **Flexible Configuration**: Configurable upstream servers, resolution modes, and all parameters
- **API Integration**: REST API and WebSocket support for custom integrations
- **Production Ready**: Structured logging, graceful shutdown, and error handling

## Stopping the Server

Stop the server gracefully with `Ctrl+C` or send a SIGTERM signal. The server will:
- Complete ongoing DNS requests
- Save cache state (if persistence is enabled)
- Close all connections properly
- Stop background tasks cleanly

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

### Web Interface Not Loading
- Check that the web port (default 8080) is not in use by another application
- Verify the web interface is enabled in configuration (`web.enabled: true`)
- Check firewall settings if accessing from another machine

### DNS Queries Not Working
- Ensure the DNS port (default 5353) is accessible
- Check upstream server connectivity
- Verify network configuration and routing

### Performance Issues
- Monitor cache hit ratios in the web interface
- Check system resource usage
- Review upstream server response times
- Consider adjusting cache size and TTL settings
