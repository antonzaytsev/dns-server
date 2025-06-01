#!/bin/bash

# DNS Server Control Script
# Simple management script for start, stop, status, and logs

set -e

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/venv"
PID_FILE="$PROJECT_ROOT/dns-server.pid"
CONFIG_FILE="$PROJECT_ROOT/config/default.yaml"
LOG_FILE="$PROJECT_ROOT/logs/dns-server.log"
PYTHON_SCRIPT="$PROJECT_ROOT/src/dns_server/main.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if server is running
is_running() {
    if [[ ! -f "$PID_FILE" ]]; then
        return 1
    fi

    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null)

    if [[ -z "$pid" ]]; then
        return 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        # PID file exists but process is dead, clean up
        rm -f "$PID_FILE"
        return 1
    fi
}

# Function to get server PID
get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE" 2>/dev/null
    fi
}

# Function to validate environment
validate_environment() {
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed or not in PATH"
        return 1
    fi

    # Check Python version
    local python_version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    IFS='.' read -r major minor <<< "$python_version"

    if [[ $major -lt 3 ]] || [[ $major -eq 3 && $minor -lt 8 ]]; then
        print_error "Python 3.8+ is required. Found Python $python_version"
        return 1
    fi

    # Check if virtual environment exists
    if [[ ! -d "$VENV_PATH" ]]; then
        print_error "Virtual environment not found at $VENV_PATH"
        print_error "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        return 1
    fi

    # Check if main script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "DNS server script not found at $PYTHON_SCRIPT"
        return 1
    fi

    # Check if config exists
    if [[ ! -f "$CONFIG_FILE" ]]; then
        print_error "Configuration file not found at $CONFIG_FILE"
        return 1
    fi

    return 0
}

# Function to start the server
start_server() {
    print_info "Starting DNS server..."

    # Check if already running
    if is_running; then
        local pid
        pid=$(get_pid)
        print_warning "DNS server is already running (PID: $pid)"
        return 0
    fi

    # Validate environment
    if ! validate_environment; then
        return 1
    fi

    # Ensure log directory exists
    mkdir -p "$(dirname "$LOG_FILE")"

    # Activate virtual environment and start server
    source "$VENV_PATH/bin/activate"

    # Start server in background
    nohup python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
    local pid=$!

    # Save PID to file
    echo "$pid" > "$PID_FILE"

    # Give the server a moment to start
    sleep 2

    # Verify server started successfully
    if is_running; then
        print_info "DNS server started successfully (PID: $pid)"
        print_info "Log file: $LOG_FILE"
        print_info "Web interface: http://localhost:8080"
        return 0
    else
        print_error "Failed to start DNS server"
        if [[ -f "$LOG_FILE" ]]; then
            print_error "Check log file for details: $LOG_FILE"
            echo "Last 5 lines of log:"
            tail -n 5 "$LOG_FILE"
        fi
        rm -f "$PID_FILE"
        return 1
    fi
}

# Function to stop the server
stop_server() {
    print_info "Stopping DNS server..."

    if ! is_running; then
        print_warning "DNS server is not running"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid
    pid=$(get_pid)

    # Send SIGTERM for graceful shutdown
    if kill -TERM "$pid" 2>/dev/null; then
        # Wait for graceful shutdown (up to 10 seconds)
        local count=0
        while [[ $count -lt 10 ]] && is_running; do
            sleep 1
            ((count++))
        done

        # Check if process stopped gracefully
        if ! is_running; then
            print_info "DNS server stopped gracefully"
            rm -f "$PID_FILE"
            return 0
        else
            print_warning "Server did not stop gracefully, forcing shutdown..."
            # Force kill
            if kill -KILL "$pid" 2>/dev/null; then
                sleep 1
                rm -f "$PID_FILE"
                print_info "DNS server forcefully stopped"
                return 0
            else
                print_error "Failed to stop DNS server"
                return 1
            fi
        fi
    else
        print_error "Failed to send SIGTERM signal"
        return 1
    fi
}

# Function to restart the server
restart_server() {
    print_info "Restarting DNS server..."
    stop_server
    sleep 1
    start_server
}

# Function to show server status
show_status() {
    echo "DNS Server Status:"
    echo "=================="

    if is_running; then
        local pid
        pid=$(get_pid)
        echo -e "Status: ${GREEN}Running${NC}"
        echo "PID: $pid"

        # Show process information if ps is available
        if command -v ps &> /dev/null; then
            echo "Process info:"
            ps -p "$pid" -o pid,ppid,cmd,etime,%cpu,%mem 2>/dev/null || echo "  Process details unavailable"
        fi

        # Show port information if available
        if command -v netstat &> /dev/null; then
            echo "Listening ports:"
            netstat -tlnp 2>/dev/null | grep "$pid" | head -5 || echo "  Port details unavailable"
        elif command -v ss &> /dev/null; then
            echo "Listening ports:"
            ss -tlnp 2>/dev/null | grep "$pid" | head -5 || echo "  Port details unavailable"
        fi

        # Show log file info
        if [[ -f "$LOG_FILE" ]]; then
            echo "Log file: $LOG_FILE"
            echo "Log size: $(du -h "$LOG_FILE" 2>/dev/null | cut -f1 || echo "unknown")"
        fi

        echo "Web interface: http://localhost:8080"

    else
        echo -e "Status: ${RED}Not running${NC}"
        if [[ -f "$PID_FILE" ]]; then
            echo "Stale PID file found (cleaning up)"
            rm -f "$PID_FILE"
        fi
    fi

    echo "Configuration: $CONFIG_FILE"
    echo "Virtual environment: $VENV_PATH"
}

# Function to show logs
show_logs() {
    local lines=${1:-50}
    local follow=${2:-false}

    if [[ ! -f "$LOG_FILE" ]]; then
        print_error "Log file not found: $LOG_FILE"
        return 1
    fi

    if [[ "$follow" == "true" ]]; then
        print_info "Following log file (Ctrl+C to stop)..."
        tail -f "$LOG_FILE"
    else
        print_info "Showing last $lines lines of log file..."
        tail -n "$lines" "$LOG_FILE"
    fi
}

# Function to show usage
show_usage() {
    echo "DNS Server Control Script"
    echo "========================"
    echo ""
    echo "Usage: $0 {start|stop|restart|status|logs} [options]"
    echo ""
    echo "Commands:"
    echo "  start           - Start the DNS server"
    echo "  stop            - Stop the DNS server"
    echo "  restart         - Restart the DNS server"
    echo "  status          - Show server status"
    echo "  logs [N]        - Show last N lines of logs (default: 50)"
    echo "  logs follow     - Follow log file in real-time"
    echo ""
    echo "Files:"
    echo "  Config: $CONFIG_FILE"
    echo "  PID file: $PID_FILE"
    echo "  Log file: $LOG_FILE"
    echo "  Python script: $PYTHON_SCRIPT"
    echo ""
    echo "Examples:"
    echo "  $0 start                 # Start the server"
    echo "  $0 status                # Check if running"
    echo "  $0 logs 100              # Show last 100 log lines"
    echo "  $0 logs follow           # Follow logs in real-time"
    echo "  $0 restart               # Restart the server"
}

# Main command handling
case "${1:-}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        show_status
        ;;
    logs)
        if [[ "${2:-}" == "follow" ]]; then
            show_logs 50 true
        else
            show_logs "${2:-50}" false
        fi
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
