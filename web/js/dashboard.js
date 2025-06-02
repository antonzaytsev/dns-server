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
        this.autoRefresh = true;
        this.refreshInterval = 30000; // 30 seconds
        this.refreshTimer = null;
        this.searchFilter = '';
        this.autoScroll = true;

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
    init() {
        console.log('Initializing DNS Dashboard');

        this.initializeEventListeners();
        this.loadTheme();
        this.fetchInitialData();
        this.startAutoRefresh();

        // Show loading overlay initially
        this.showLoading();

        // Hide loading after initial load
        setTimeout(() => {
            this.hideLoading();
        }, 2000);
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
     * Start auto-refresh timer
     */
    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        if (this.autoRefresh) {
            this.refreshTimer = setInterval(() => {
                this.refreshData();
            }, this.refreshInterval);
        }
    }

    /**
     * Refresh data from API
     */
    async refreshData() {
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.add('spinning');
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/status`);
            if (response.ok) {
                const data = await response.json();
                this.updateServerStatus(data);
                this.showNotification('Data refreshed', 'info');
            }
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showNotification('Failed to refresh data', 'error');
        } finally {
            if (refreshBtn) {
                refreshBtn.classList.remove('spinning');
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
                const searchText = `${query.domain} ${query.client_ip} ${query.query_type} ${query.response_code}`.toLowerCase();
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

        // Format response code
        const responseClass = ['NOERROR', 'SUCCESS'].includes(query.response_code) ? 'success' : 'error';

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
                <span class="response-code ${responseClass}">${query.response_code || '-'}</span>
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
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        if (window.chartsManager) {
            window.chartsManager.destroy();
        }

        if (window.wsManager) {
            window.wsManager.disconnect();
        }
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
