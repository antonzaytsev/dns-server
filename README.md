# DNS Server

A high-performance, async DNS server written in Python with real-time monitoring and caching capabilities.

## Features

- **High Performance**: Built with asyncio for concurrent request handling
- **Real-time Monitoring**: Web dashboard with live DNS query tracking
- **Intelligent Caching**: Configurable DNS response caching with TTL management
- **Security Features**: Rate limiting, network ACLs, and query validation
- **Multiple Protocols**: Support for both UDP and TCP DNS queries
- **Upstream Forwarding**: Configurable upstream DNS servers with failover
- **Structured Logging**: JSON-formatted logs with request tracking
- **Docker Support**: Containerized deployment with Docker Compose
- **Health Checks**: Built-in health monitoring and metrics

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd dns-server
   ```

2. **Start the DNS server**:
   ```bash
   docker-compose up -d
   ```

3. **Access the web dashboard**:
   Open `http://localhost:9980` in your browser

4. **Test DNS queries**:
   ```bash
   nslookup google.com 127.0.0.1 -port=9953
   dig @127.0.0.1 -p 9953 example.com
   ```

### Client IP Logging

#### Issue: All Client IPs Show the Same Address

If you notice that all DNS queries in the dashboard show the same client IP (e.g., `192.168.147.1`), this is typically due to Docker networking configuration. The DNS server is receiving all requests through Docker's bridge network, masking the real client IPs.

#### Solution 1: Use Host Networking (Recommended)

The docker-compose.yml has been configured to use host networking mode, which allows the DNS server to see real client IPs:

```yaml
services:
  dns-server:
    network_mode: host
    # ... other configuration
```

With host networking:
- ✅ Real client IPs are preserved
- ✅ Better performance (no NAT overhead)
- ⚠️ Container uses host's network stack directly

#### Solution 2: Enable Debug Logging

To troubleshoot client IP issues, enable detailed debugging in `config/default.yaml`:

```yaml
security:
  debug_client_ip: true  # Enable detailed client IP debugging logs
```

This will log detailed information about each connection including:
- Raw socket addresses
- Transport information
- Connection metadata

#### Solution 3: Alternative Docker Networking

If you cannot use host networking, you can try these alternatives:

1. **Bridge with published ports** (less ideal):
   ```yaml
   services:
     dns-server:
       ports:
         - "9953:9953/udp"
         - "9953:9953/tcp"
         - "9980:9980/tcp"
       # Note: This may still show Docker gateway IP
   ```

2. **Custom bridge network with IP forwarding**:
   ```yaml
   networks:
     dns-network:
       driver: bridge
       driver_opts:
         com.docker.network.bridge.enable_ip_masquerade: "false"
   ```

#### Verifying Client IP Detection

After making changes, restart the DNS server and test with queries from different machines:

```bash
# From machine 1
nslookup google.com <your-server-ip> -port=9953

# From machine 2
dig @<your-server-ip> -p 9953 example.com
```

Check the web dashboard at `http://<your-server-ip>:9980` to verify that different client IPs are now being logged correctly.

## Configuration

### Basic Configuration

Edit `config/default.yaml` to customize the DNS server:

```yaml
# Server Configuration
server:
  bind_address: "0.0.0.0"  # Bind to all interfaces
  dns_port: 9953           # DNS server port
  web_port: 9980           # Web dashboard port

# Upstream DNS Servers
upstream_servers:
  - "8.8.8.8"        # Google DNS
  - "1.1.1.1"        # Cloudflare DNS
  - "208.67.222.222" # OpenDNS

# Security Configuration
security:
  rate_limit_per_ip: 100      # Max queries per IP per minute
  debug_client_ip: false      # Enable client IP debugging
  allowed_networks: ["0.0.0.0/0"]  # Allowed networks (CIDR)
```

### Advanced Configuration

See the complete configuration schema in `src/dns_server/config/schema.py` for all available options including:
- Cache settings (size, TTL)
- Logging configuration
- Performance tuning
- Security features

## Development

### Local Development

1. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the server**:
   ```bash
   python -m src.dns_server.main --config config/default.yaml
   ```

### Testing

Run the test suite:
```bash
pytest src/tests/
```

Run performance tests:
```bash
python test_performance.py
```

## Monitoring and Logging

### Web Dashboard

The web dashboard provides real-time monitoring:
- Live DNS query stream
- Performance metrics
- Cache statistics
- Server health status

### Structured Logging

All logs are output in JSON format for easy parsing:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "request_id": "abc123",
  "client_ip": "192.168.1.100",
  "query_type": "A",
  "domain": "example.com",
  "response_code": "NOERROR",
  "response_time_ms": 45.2,
  "cache_hit": false,
  "upstream_server": "8.8.8.8"
}
```

### Health Checks

Check server health:
```bash
python -m src.dns_server.main --health-check
```

## Troubleshooting

### Common Issues

1. **Permission denied on port 53**:
   - Use non-privileged ports (like 9953) for development
   - Run with sudo for privileged ports in production

2. **Client IPs not showing correctly**:
   - Use host networking mode in Docker
   - Enable debug_client_ip for troubleshooting

3. **High memory usage**:
   - Adjust cache size in configuration
   - Monitor cache hit ratios

4. **Slow query responses**:
   - Check upstream server latency
   - Review cache configuration
   - Monitor resource usage

### Debug Mode

Enable debug logging for detailed troubleshooting:

```yaml
logging:
  level: "DEBUG"
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request
