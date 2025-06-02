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
   docker-compose up -d --build
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

If you notice that all DNS queries in the dashboard show the same client IP (e.g., `172.17.0.1`), this is typically due to Docker networking configuration. The DNS server is receiving all requests through Docker's bridge network, masking the real client IPs.

#### Solution 1: Enable Debug Logging

To troubleshoot client IP issues, enable detailed debugging in `config/default.yaml`:

```yaml
security:
  debug_client_ip: true  # Enable detailed client IP debugging logs
```

This will log detailed information about each connection including:
- Raw socket addresses
- Transport information
- Connection metadata

#### Solution 2: Use Host Networking (Alternative)

If you need to see real client IPs, you can modify `docker-compose.yml` to use host networking:

```yaml
services:
  dns-server:
    network_mode: host
    # Remove the ports section when using host networking
```

With host networking:
- ✅ Real client IPs are preserved
- ✅ Better performance (no NAT overhead)
- ⚠️ Container uses host's network stack directly
- ⚠️ May require additional system configuration

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
  dns_port: 53             # Container internal DNS port (exposed as 9953)
  web_port: 80             # Container internal web port (exposed as 9980)

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

### Code Quality

Run code quality checks and formatters manually when needed:

#### All Quality Checks (Recommended)
Run all linters and formatters in one command:
```bash
docker-compose exec dns-server bash -c "cd /app && black src/ && isort src/ && flake8 src/"
```

#### Individual Tools

**Code Formatting with Black:**
```bash
# Format code
docker-compose exec dns-server black src/

# Check formatting without changing files
docker-compose exec dns-server black --check src/
```

**Import Sorting with isort:**
```bash
# Sort imports
docker-compose exec dns-server isort src/

# Check import sorting without changing files
docker-compose exec dns-server isort --check-only src/
```

**Linting with flake8:**
```bash
# Run linting
docker-compose exec dns-server flake8 src/
```

**Other Quality Checks:**
```bash
# Check for trailing whitespace
docker-compose exec dns-server bash -c "cd /app && find src/ -name '*.py' -exec grep -l '[[:space:]]$' {} \;"

# Check YAML files
docker-compose exec dns-server python -c "import yaml; yaml.safe_load(open('config/default.yaml'))"
```

#### Before Committing
It's recommended to run these commands before committing code:
```bash
# Format and lint everything
docker-compose exec dns-server bash -c "cd /app && black src/ && isort src/ && flake8 src/ && echo 'All checks passed!'"
```

#### IDE Integration
For a better development experience, configure your IDE to run these tools automatically:
- **VS Code**: Install Python, Black, isort, and flake8 extensions
- **PyCharm**: Enable Black and flake8 in settings

## Monitoring and Logging

### Web Dashboard

The web dashboard provides real-time monitoring:
- Live DNS query stream
- Performance metrics
- Cache statistics
- Server health status

### Structured Logging

DNS queries are logged in JSON format to `logs/dns-server.log`:

```json
{"datetime": "2025-06-01 22:12:13 UTC", "domain": "google.com", "ip_address": ["77.88.55.242"]}
```

Application logs are written to `logs/app.log` in structured JSON format:

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

Or via Docker:
```bash
docker-compose exec dns-server python /app/src/dns_server/main.py --config /app/config/default.yaml --health-check
```

## Troubleshooting

### Common Issues

1. **Permission denied on port 53**:
   - The DNS server uses port 9953 (non-privileged) by default
   - No special permissions required for the default configuration
   - For port 53, see advanced configuration below

2. **Port already in use**:
   - Check if another service is using port 9953: `lsof -i :9953`
   - Check if another service is using port 9980: `lsof -i :9980`
   - Stop conflicting services or change ports in configuration

3. **Client IPs not showing correctly**:
   - This is normal with Docker bridge networking
   - Enable debug_client_ip for troubleshooting
   - Consider using host networking if real IPs are needed

4. **High memory usage**:
   - Adjust cache size in configuration
   - Monitor cache hit ratios
   - Check for memory leaks in logs

5. **Slow query responses**:
   - Check upstream server latency
   - Review cache configuration
   - Monitor resource usage

### Debug Mode

Enable debug logging for detailed troubleshooting:

```yaml
logging:
  level: "DEBUG"
```

### Docker Issues

1. **Container fails to start**:
   ```bash
   # Check container logs
   docker-compose logs dns-server
   
   # Check container status
   docker-compose ps
   ```

2. **Permission issues with log files**:
   ```bash
   # Create log directories with proper permissions
   mkdir -p logs
   chmod 755 logs
   ```

3. **Network connectivity issues**:
   ```bash
   # Test container networking
   docker-compose exec dns-server ping 8.8.8.8
   
   # Check port binding
   docker-compose port dns-server 53
   ```

### Advanced Configuration: Using Standard Port 53

If you need to run on the standard DNS port 53, you can modify the configuration:

1. **Update docker-compose.yml**:
   ```yaml
   services:
     dns-server:
       # Comment out the user line to run as root
       # user: "${UID:-1000}:${GID:-1000}"
       ports:
         - "53:53/udp"     # DNS UDP
         - "53:53/tcp"     # DNS TCP
         - "9980:80/tcp"   # Web interface
   ```

2. **Run with elevated privileges**:
   ```bash
   sudo docker-compose up -d --build
   ```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request
