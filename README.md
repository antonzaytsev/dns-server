# DNS Server

A high-performance, configurable DNS server with web interface and advanced caching capabilities.

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
- **DNS queries**: `127.0.0.1:9953`
- **Web interface**: `http://127.0.0.1:8080`

## Configuration

### Custom Configuration

Use a custom configuration file:
```bash
python src/dns_server/main.py --config /path/to/your/config.yaml
```

### Default Configuration

The server uses `config/default.yaml` by default. Key settings you can modify:

- **DNS Port**: Change `server.dns_port` (default: 9953)
- **Web Port**: Change `server.web_port` (default: 8080)
- **Upstream Servers**: Modify `upstream_servers` list
- **Cache Size**: Adjust `cache.max_size_mb`
- **Bind Address**: Change `server.bind_address`

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
dig @127.0.0.1 -p 9953 google.com

# Using nslookup
nslookup google.com 127.0.0.1:9953
```

## Web Interface

Access the web interface at `http://127.0.0.1:8080` to:
- Monitor DNS queries in real-time
- View performance metrics
- Check cache status
- See query history

## Performance Testing

Run the included performance test:
```bash
python test_performance.py
```

## Features

- **High Performance**: Optimized with uvloop and connection pooling
- **Caching**: Intelligent DNS response caching
- **Web Interface**: Real-time monitoring and statistics
- **Security**: Rate limiting and network filtering
- **Monitoring**: Built-in health checks and performance metrics
- **Flexible**: Configurable upstream servers and resolution modes

## Stopping the Server

Stop the server with `Ctrl+C` or send a SIGTERM signal.

## Common Use Cases

### Development DNS Server
Use as a local DNS server for development with custom configurations.

### DNS Proxy
Forward DNS queries to multiple upstream servers with caching.

### Performance Testing
Benchmark DNS resolution performance with built-in monitoring tools.
