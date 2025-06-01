/**
 * WebSocket Manager for DNS Server Dashboard
 *
 * Handles real-time communication with the DNS server backend
 * for live updates, status changes, and query monitoring.
 */

class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.isConnected = false;
        this.messageHandlers = new Map();
        this.queryBuffer = [];
        this.maxQueryBuffer = 1000;

        // Bind methods
        this.connect = this.connect.bind(this);
        this.onOpen = this.onOpen.bind(this);
        this.onMessage = this.onMessage.bind(this);
        this.onClose = this.onClose.bind(this);
        this.onError = this.onError.bind(this);
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        try {
            // Determine WebSocket URL
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            const wsUrl = `${protocol}//${host}/ws`;

            console.log('Connecting to WebSocket:', wsUrl);
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = this.onOpen;
            this.ws.onmessage = this.onMessage;
            this.ws.onclose = this.onClose;
            this.ws.onerror = this.onError;

            // Update connection status
            this.updateConnectionStatus('connecting');

        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.scheduleReconnect();
        }
    }

    /**
     * Handle WebSocket connection open
     */
    onOpen(event) {
        console.log('WebSocket connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;

        // Clear any pending reconnect timer
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        // Update connection status
        this.updateConnectionStatus('connected');

        // Subscribe to events
        this.send({
            type: 'subscribe',
            events: ['dns_query', 'stats_update', 'cache_event', 'server_event']
        });

        // Request initial status
        this.send({
            type: 'get_status'
        });

        // Show success notification
        this.showNotification('Connected to DNS server', 'success');
    }

    /**
     * Handle incoming WebSocket messages
     */
    onMessage(event) {
        try {
            const message = JSON.parse(event.data);
            console.log('WebSocket message:', message.type, message);

            // Update last update time
            this.updateLastUpdateTime();

            // Handle different message types
            switch (message.type) {
                case 'welcome':
                    this.handleWelcome(message);
                    break;
                case 'server_status':
                    this.handleServerStatus(message);
                    break;
                case 'dns_query':
                    this.handleDnsQuery(message);
                    break;
                case 'stats_update':
                    this.handleStatsUpdate(message);
                    break;
                case 'cache_event':
                    this.handleCacheEvent(message);
                    break;
                case 'server_event':
                    this.handleServerEvent(message);
                    break;
                case 'recent_logs':
                    this.handleRecentLogs(message);
                    break;
                case 'subscription_confirmed':
                    console.log('Subscribed to events:', message.events);
                    break;
                case 'pong':
                    // Handle ping/pong for keep-alive
                    break;
                default:
                    console.warn('Unknown message type:', message.type);
            }

            // Call any registered handlers
            const handlers = this.messageHandlers.get(message.type);
            if (handlers) {
                handlers.forEach(handler => {
                    try {
                        handler(message);
                    } catch (error) {
                        console.error('Error in message handler:', error);
                    }
                });
            }

        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    /**
     * Handle WebSocket connection close
     */
    onClose(event) {
        console.log('WebSocket disconnected:', event.code, event.reason);
        this.isConnected = false;

        // Update connection status
        this.updateConnectionStatus('disconnected');

        // Schedule reconnection if not intentional close
        if (event.code !== 1000) {
            this.scheduleReconnect();
        }

        // Show notification
        this.showNotification('Disconnected from DNS server', 'warning');
    }

    /**
     * Handle WebSocket errors
     */
    onError(event) {
        console.error('WebSocket error:', event);
        this.updateConnectionStatus('error');
    }

    /**
     * Send message to WebSocket server
     */
    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                this.ws.send(JSON.stringify(message));
                return true;
            } catch (error) {
                console.error('Error sending WebSocket message:', error);
                return false;
            }
        } else {
            console.warn('WebSocket not connected, cannot send message:', message);
            return false;
        }
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this.showNotification('Failed to reconnect to DNS server', 'error');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff

        console.log(`Scheduling reconnection attempt ${this.reconnectAttempts} in ${delay}ms`);

        this.reconnectTimer = setTimeout(() => {
            console.log(`Reconnection attempt ${this.reconnectAttempts}`);
            this.connect();
        }, delay);
    }

    /**
     * Update connection status display
     */
    updateConnectionStatus(status) {
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        const wsStatus = document.getElementById('ws-status');

        if (statusDot && statusText) {
            statusDot.className = 'status-dot';

            switch (status) {
                case 'connected':
                    statusDot.classList.add('connected');
                    statusText.textContent = 'Connected';
                    break;
                case 'connecting':
                    statusDot.classList.add('connecting');
                    statusText.textContent = 'Connecting...';
                    break;
                case 'disconnected':
                    statusText.textContent = 'Disconnected';
                    break;
                case 'error':
                    statusText.textContent = 'Connection Error';
                    break;
            }
        }

        if (wsStatus) {
            wsStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }

    /**
     * Update last update time
     */
    updateLastUpdateTime() {
        const lastUpdate = document.getElementById('last-update');
        if (lastUpdate) {
            lastUpdate.textContent = new Date().toLocaleTimeString();
        }
    }

    /**
     * Handle welcome message
     */
    handleWelcome(message) {
        console.log('Welcome message:', message.message);
    }

    /**
     * Handle server status message
     */
    handleServerStatus(message) {
        // Update server status in dashboard
        if (window.dashboard) {
            window.dashboard.updateServerStatus(message);
        }
    }

    /**
     * Handle DNS query message
     */
    handleDnsQuery(message) {
        // Add to query buffer
        this.queryBuffer.unshift(message.query);

        // Limit buffer size
        if (this.queryBuffer.length > this.maxQueryBuffer) {
            this.queryBuffer = this.queryBuffer.slice(0, this.maxQueryBuffer);
        }

        // Update dashboard
        if (window.dashboard) {
            window.dashboard.addDnsQuery(message.query);
        }
    }

    /**
     * Handle stats update message
     */
    handleStatsUpdate(message) {
        // Update dashboard stats
        if (window.dashboard) {
            window.dashboard.updateStats(message.dns_stats, message.cache_stats);
        }
    }

    /**
     * Handle cache event message
     */
    handleCacheEvent(message) {
        console.log('Cache event:', message.event_type, message.data);

        // Show notification for cache operations
        switch (message.event_type) {
            case 'cleared':
                this.showNotification('Cache cleared successfully', 'success');
                break;
            case 'flushed':
                this.showNotification('Cache flushed successfully', 'success');
                break;
        }
    }

    /**
     * Handle server event message
     */
    handleServerEvent(message) {
        console.log('Server event:', message.event_type, message.message);

        // Show notification for important server events
        const eventType = message.event_type;
        if (eventType === 'error' || eventType === 'warning') {
            this.showNotification(message.message, eventType);
        }
    }

    /**
     * Handle recent logs message
     */
    handleRecentLogs(message) {
        // Update dashboard with recent logs
        if (window.dashboard) {
            window.dashboard.setRecentQueries(message.logs);
        }
    }

    /**
     * Register message handler
     */
    onMessage(type, handler) {
        if (!this.messageHandlers.has(type)) {
            this.messageHandlers.set(type, []);
        }
        this.messageHandlers.get(type).push(handler);
    }

    /**
     * Unregister message handler
     */
    offMessage(type, handler) {
        const handlers = this.messageHandlers.get(type);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index !== -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Get query buffer
     */
    getQueryBuffer() {
        return [...this.queryBuffer];
    }

    /**
     * Clear query buffer
     */
    clearQueryBuffer() {
        this.queryBuffer = [];
    }

    /**
     * Send ping to keep connection alive
     */
    ping() {
        this.send({ type: 'ping' });
    }

    /**
     * Request recent logs
     */
    requestRecentLogs(limit = 50) {
        this.send({
            type: 'get_recent_logs',
            limit: limit
        });
    }

    /**
     * Disconnect WebSocket
     */
    disconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }

        this.isConnected = false;
        this.updateConnectionStatus('disconnected');
    }

    /**
     * Show notification (implementation depends on dashboard)
     */
    showNotification(message, type = 'info') {
        if (window.dashboard && window.dashboard.showNotification) {
            window.dashboard.showNotification(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
}

// Create global WebSocket manager instance
window.wsManager = new WebSocketManager();

// Auto-connect when script loads
document.addEventListener('DOMContentLoaded', () => {
    window.wsManager.connect();

    // Set up periodic ping to keep connection alive
    setInterval(() => {
        if (window.wsManager.isConnected) {
            window.wsManager.ping();
        }
    }, 30000); // Ping every 30 seconds
});
