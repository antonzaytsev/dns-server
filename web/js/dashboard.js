/**
 * DNS Server Dashboard Controller
 *
 * Main controller for the DNS server dashboard interface.
 * Manages data updates, user interactions, API calls, and UI state.
 */

class DNSDashboard {
    constructor() {
        this.apiBaseUrl = '/api';
        this.queries = [];
        this.maxQueries = 1000;
        this.currentTheme = 'light';
        this.autoScroll = true;
        this.autoRefresh = true;
        this.refreshInterval = 5000; // 5 seconds
        this.refreshTimer = null;
        
        // Polling timers
        this.statusPollingTimer = null;
        this.queriesPollingTimer = null;
        this.statusPollingInterval = 2000; // 2 seconds for status/stats
        this.queriesPollingInterval = 3000; // 3 seconds for queries
        
        // Search and filtering
        this.searchFilter = '';
        this.lastQueryCount = 0; // Track if new queries arrived

        // Bind methods
        this.init = this.init.bind(this);
        this.updateStats = this.updateStats.bind(this);
        this.addDnsQuery = this.addDnsQuery.bind(this);
        this.toggleTheme = this.toggleTheme.bind(this);
        this.refreshData = this.refreshData.bind(this);
    }

    /**
     * Initialize the dashboard
     */
    async init() {
        console.log('🚀 DNS Dashboard: Initializing...');

        // Load theme
        this.loadTheme();

        // Initialize event listeners
        this.initializeEventListeners();

        // Start data fetching and polling
        await this.fetchInitialData();
        this.startPolling();
        
        console.log('✅ DNS Dashboard: Initialized successfully');
    }

    initializeEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', this.refreshData.bind(this));
        }

        // Theme toggle
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', this.toggleTheme.bind(this));
        }

        // Clear logs button
        const clearLogsBtn = document.getElementById('clear-logs');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', this.clearLogs.bind(this));
        }

        // Search input
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', this.filterQueries.bind(this));
        }

        // Auto-scroll checkbox
        const autoScrollCheckbox = document.getElementById('auto-scroll');
        if (autoScrollCheckbox) {
            autoScrollCheckbox.addEventListener('change', (e) => {
                this.autoScroll = e.target.checked;
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.refreshData();
            }
            if (e.key === 'c' && (e.ctrlKey || e.metaKey) && e.shiftKey) {
                e.preventDefault();
                this.clearLogs();
            }
        });
    }

    /**
     * Load theme from localStorage
     */
    loadTheme() {
        const savedTheme = localStorage.getItem('dns-dashboard-theme') || 'light';
        this.setTheme(savedTheme);
    }

    /**
     * Set theme
     */
    setTheme(theme) {
        this.currentTheme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('dns-dashboard-theme', theme);

        // Update theme toggle button
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            themeToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
        }

        // Dispatch theme change event for charts
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { isDark: theme === 'dark' }
        }));
    }

    /**
     * Toggle theme
     */
    toggleTheme() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
    }

    /**
     * Show loading overlay
     */
    showLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.remove('hidden');
        }
    }

    /**
     * Hide loading overlay
     */
    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }

    /**
     * Fetch initial data from API
     */
    async fetchInitialData() {
        try {
            // Fetch server status
            const statusResponse = await fetch(`${this.apiBaseUrl}/status`);
            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                this.updateServerStatus(statusData);
            }

            // Fetch recent logs
            const logsResponse = await fetch(`${this.apiBaseUrl}/logs/recent?limit=50`);
            if (logsResponse.ok) {
                const logsData = await logsResponse.json();
                this.setRecentQueries(logsData.logs || []);
            }

        } catch (error) {
            console.error('Error fetching initial data:', error);
            this.showNotification('Failed to load initial data', 'error');
        }
    }

    /**
     * Start HTTP polling for real-time updates
     */
    startPolling() {
        console.log('🔄 Starting HTTP polling for real-time updates');
        
        // Update status indicators
        this.updatePollingStatus('active');
        
        // Poll server status and statistics
        this.statusPollingTimer = setInterval(async () => {
            try {
                const response = await fetch(`${this.apiBaseUrl}/status`);
                if (response.ok) {
                    const data = await response.json();
                    this.updateServerStatus(data);
                    this.updatePollingStatus('active');
                    this.updateLastUpdateTime();
                } else {
                    this.updatePollingStatus('error');
                }
            } catch (error) {
                console.error('Status polling error:', error);
                this.updatePollingStatus('error');
            }
        }, this.statusPollingInterval);

        // Poll for new queries
        this.queriesPollingTimer = setInterval(async () => {
            try {
                const response = await fetch(`${this.apiBaseUrl}/queries?limit=50`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.logs && data.logs.length > 0) {
                        this.updateQueriesIfChanged(data.logs);
                    }
                }
            } catch (error) {
                console.error('Queries polling error:', error);
            }
        }, this.queriesPollingInterval);
    }

    /**
     * Stop HTTP polling
     */
    stopPolling() {
        console.log('⏹️ Stopping HTTP polling');
        
        if (this.statusPollingTimer) {
            clearInterval(this.statusPollingTimer);
            this.statusPollingTimer = null;
        }
        
        if (this.queriesPollingTimer) {
            clearInterval(this.queriesPollingTimer);
            this.queriesPollingTimer = null;
        }
        
        this.updatePollingStatus('stopped');
    }

    /**
     * Update polling status display
     */
    updatePollingStatus(status) {
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        const pollingStatus = document.getElementById('polling-status');

        if (statusDot && statusText) {
            statusDot.className = 'status-dot';

            switch (status) {
                case 'active':
                    statusDot.classList.add('connected');
                    statusText.textContent = 'Active';
                    break;
                case 'error':
                    statusDot.classList.add('error');
                    statusText.textContent = 'Error';
                    break;
                case 'stopped':
                    statusText.textContent = 'Stopped';
                    break;
                default:
                    statusText.textContent = 'Loading...';
            }
        }

        if (pollingStatus) {
            pollingStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
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
     * Update queries if new ones arrived
     */
    updateQueriesIfChanged(newQueries) {
        // Check if we have new queries by comparing the first query timestamp
        if (newQueries.length === 0) return;
        
        const latestTimestamp = newQueries[0].timestamp;
        const currentLatestTimestamp = this.queries.length > 0 ? this.queries[0].timestamp : null;
        
        // If we have new queries, update the list
        if (!currentLatestTimestamp || latestTimestamp !== currentLatestTimestamp) {
            console.log('📊 New queries detected, updating dashboard');
            
            // Find truly new queries by comparing timestamps
            const newEntries = [];
            for (const query of newQueries) {
                const exists = this.queries.find(q => q.timestamp === query.timestamp && q.request_id === query.request_id);
                if (!exists) {
                    newEntries.push(query);
                }
            }
            
            // Add new queries to the beginning of the array
            if (newEntries.length > 0) {
                this.queries = [...newEntries, ...this.queries].slice(0, this.maxQueries);
                this.renderQueries();
                
                // Update charts with new queries
                newEntries.forEach(query => {
                    if (window.chartsManager) {
                        window.chartsManager.addDnsQuery(query);
                    }
                });
                
                console.log(`✅ Added ${newEntries.length} new DNS queries`);
            }
        }
    }

    /**
     * Update server status display
     */
    updateServerStatus(data) {
        // Update server info
        this.updateElement('server-status', data.server?.status || 'Unknown');
        this.updateElement('server-version', data.server?.version || '-');

        // Calculate and display uptime
        if (data.server?.uptime_seconds) {
            const uptime = this.formatUptime(data.server.uptime_seconds);
            this.updateElement('server-uptime', uptime);
        }

        // Update DNS stats
        if (data.dns) {
            this.updateElement('total-queries', data.dns.total_queries || 0);
            this.updateElement('udp-queries', data.dns.udp_queries || 0);
            this.updateElement('tcp-queries', data.dns.tcp_queries || 0);
            this.updateElement('error-count', data.dns.errors || 0);

            // Calculate QPS
            if (data.dns.total_queries && data.server?.uptime_seconds) {
                const qps = (data.dns.total_queries / data.server.uptime_seconds).toFixed(2);
                this.updateElement('queries-per-second', qps);
            }

            // Update average response time
            if (data.dns.response_times && data.dns.response_times.length > 0) {
                const avgTime = data.dns.response_times.reduce((a, b) => a + b, 0) / data.dns.response_times.length;
                this.updateElement('avg-response-time', avgTime.toFixed(2) + ' ms');
            }
        }

        // Update WebSocket clients
        if (data.websocket) {
            this.updateElement('websocket-clients', data.websocket.connected_clients || 0);
        }

        // Update system stats if available
        if (data.performance && data.performance.system) {
            this.updateElement('system-memory', (data.performance.system.memory_mb || 0).toFixed(1) + ' MB');
        }

        // Update charts
        this.updateStats(data.dns);
    }

    /**
     * Update statistics (called by WebSocket or API)
     */
    updateStats(dnsStats) {
        if (window.chartsManager) {
            window.chartsManager.updateCharts(dnsStats);
        }
    }

    /**
     * Add new DNS query to display
     */
    addDnsQuery(query) {
        console.log('🚀 Dashboard: Adding new DNS query to UI:', query);

        // Add to queries array
        this.queries.unshift(query);

        // Limit array size
        if (this.queries.length > this.maxQueries) {
            this.queries = this.queries.slice(0, this.maxQueries);
        }

        // Update charts
        if (window.chartsManager) {
            window.chartsManager.addDnsQuery(query);
        }

        // Add new query to top of list
        console.log('🖼️ Dashboard: Adding new query to top of list');
        this.addNewQueryToTop(query);

        console.log('✅ Dashboard: Real-time DNS query update complete');
    }

    /**
     * Add a new query to the top of the list
     */
    addNewQueryToTop(query) {
        const queriesList = document.getElementById('queries-list');
        if (!queriesList) return;

        // Create new query row
        const newRow = this.createQueryRow(query);

        // Insert at the top of the list
        queriesList.insertBefore(newRow, queriesList.firstChild);

        // Remove excess rows if needed
        const maxDisplayRows = 100; // Limit displayed rows for performance
        const rows = queriesList.children;
        while (rows.length > maxDisplayRows) {
            queriesList.removeChild(rows[rows.length - 1]);
        }

        // Auto-scroll to top to show new query
        if (this.autoScroll && !this.searchFilter) {
            queriesList.scrollTop = 0;
        }
    }

    /**
     * Set recent queries (initial load)
     */
    setRecentQueries(queries) {
        this.queries = queries.slice(0, this.maxQueries);
        this.renderQueries();
    }

    /**
     * Render queries list
     */
    renderQueries() {
        const queriesList = document.getElementById('queries-list');
        if (!queriesList) return;

        // Filter queries based on search
        let filteredQueries = this.queries;
        if (this.searchFilter) {
            filteredQueries = this.queries.filter(query => {
                const searchText = `${query.domain} ${query.client_ip} ${query.query_type} ${query.response_code} ${query.error || ''}`.toLowerCase();
                return searchText.includes(this.searchFilter);
            });
        }

        // Clear existing content
        queriesList.innerHTML = '';

        // Render filtered queries (without highlight for bulk rendering)
        filteredQueries.forEach(query => {
            const queryRow = this.createQueryRow(query);
            queriesList.appendChild(queryRow);
        });

        // Auto-scroll to top for new queries (since we want newest first)
        if (this.autoScroll && !this.searchFilter) {
            setTimeout(() => {
                queriesList.scrollTop = 0;
            }, 100);
        }
    }

    /**
     * Create query row element
     */
    createQueryRow(query) {
        const row = document.createElement('div');
        row.className = 'query-row';

        // Format timestamp
        const timestamp = query.timestamp ? new Date(query.timestamp).toLocaleTimeString() : '-';

        // Format response code and error message
        const responseClass = ['NOERROR', 'SUCCESS'].includes(query.response_code) ? 'success' : 'error';
        let responseContent = `<span class="response-code ${responseClass}">${query.response_code || '-'}</span>`;
        
        // Add error message if present, or response code explanation for failed queries
        if (query.error) {
            responseContent += `<div class="error-message" title="${query.error}">${query.error}</div>`;
        } else if (query.response_code && !['NOERROR', 'SUCCESS'].includes(query.response_code)) {
            // Show response code explanation for failed queries
            const explanations = {
                'NXDOMAIN': 'Domain does not exist',
                'SERVFAIL': 'Server failure',
                'REFUSED': 'Query refused',
                'FORMERR': 'Format error',
                'NOTIMP': 'Not implemented',
                'NXRRSET': 'RRset does not exist'
            };
            const explanation = explanations[query.response_code] || `DNS query failed: ${query.response_code}`;
            responseContent += `<div class="error-message" title="${explanation}">${explanation}</div>`;
        }

        // Extract IP addresses from response_data
        let ipAddresses = '-';
        if (query.response_data && query.response_data.length > 0) {
            const ips = [];
            query.response_data.forEach(data => {
                // Skip entries that start with "rdata=" as they contain DNS binary data
                if (data.toString().startsWith("rdata=")) {
                    return;
                }
                
                // Extract IP addresses from various response formats
                // Handle formats like "example.com. 1.2.3.4" or just "1.2.3.4"
                const parts = data.toString().split(/\s+/);
                let candidateIp = null;
                
                if (parts.length >= 2) {
                    // Format: "example.com. 1.2.3.4"
                    candidateIp = parts[parts.length - 1];
                } else if (parts.length === 1) {
                    // Format: "1.2.3.4"
                    candidateIp = parts[0];
                }
                
                // Validate that it's actually an IP address (IPv4 or IPv6)
                if (candidateIp && this.isValidIpAddress(candidateIp)) {
                    ips.push(candidateIp);
                }
            });
            
            if (ips.length > 0) {
                ipAddresses = ips.join(', ');
            }
        }

        row.innerHTML = `
            <div class="query-col timestamp-col">${timestamp}</div>
            <div class="query-col client-col">${query.client_ip || '-'}</div>
            <div class="query-col domain-col" title="${query.domain || '-'}">${query.domain || '-'}</div>
            <div class="query-col type-col">${query.query_type || '-'}</div>
            <div class="query-col response-col">
                ${responseContent}
            </div>
            <div class="query-col ip-addresses-col" title="${ipAddresses}">${ipAddresses}</div>
            <div class="query-col time-col">${query.response_time_ms || '-'}</div>
        `;

        return row;
    }

    /**
     * Filter queries based on search input
     */
    filterQueries() {
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            this.searchFilter = searchInput.value.toLowerCase();
        }
        this.renderQueries();
    }

    /**
     * Clear all queries
     */
    clearLogs() {
        this.queries = [];
        this.renderQueries();

        // Clear charts data
        if (window.chartsManager) {
            window.chartsManager.clearAllData();
        }

        this.showNotification('Query logs cleared', 'info');
    }

    /**
     * Update element text content
     */
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    /**
     * Format uptime in human-readable format
     */
    formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);

        if (days > 0) {
            return `${days}d ${hours}h ${minutes}m`;
        } else if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    }

    /**
     * Show notification toast
     */
    showNotification(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        // Add to container
        container.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 5000);
    }

    /**
     * Get dashboard data for export
     */
    exportData() {
        return {
            queries: this.queries,
            theme: this.currentTheme,
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Destroy dashboard and cleanup
     */
    destroy() {
        console.log('🧹 Cleaning up DNS Dashboard');
        
        // Stop polling
        this.stopPolling();
        
        // Stop auto-refresh timer if it exists
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        // Destroy charts
        if (window.chartsManager) {
            window.chartsManager.destroy();
        }

        console.log('✅ DNS Dashboard cleanup complete');
    }

    /**
     * Validate IP address
     */
    isValidIpAddress(ip) {
        return (/^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/.test(ip) ||
                /^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$/.test(ip) ||
                /^::1$/.test(ip) ||
                /^::ffff:[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$/.test(ip));
    }

    /**
     * Refresh data from API manually
     */
    async refreshData() {
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.add('spinning');
        }

        try {
            // Fetch current status
            const statusResponse = await fetch(`${this.apiBaseUrl}/status`);
            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                this.updateServerStatus(statusData);
            }

            // Fetch recent queries
            const queriesResponse = await fetch(`${this.apiBaseUrl}/queries?limit=50`);
            if (queriesResponse.ok) {
                const queriesData = await queriesResponse.json();
                if (queriesData.logs) {
                    this.queries = queriesData.logs.slice(0, this.maxQueries);
                    this.renderQueries();
                }
            }

            this.showNotification('Data refreshed', 'info');
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showNotification('Failed to refresh data', 'error');
        } finally {
            if (refreshBtn) {
                refreshBtn.classList.remove('spinning');
            }
        }
    }
}

// Create global dashboard instance
window.dashboard = new DNSDashboard();

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard.init();
});

// Handle page unload
window.addEventListener('beforeunload', () => {
    if (window.dashboard) {
        window.dashboard.destroy();
    }
});
