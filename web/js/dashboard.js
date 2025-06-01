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
        
        this.setupEventListeners();
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

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Theme toggle
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', this.toggleTheme);
        }

        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', this.refreshData);
        }

        // Cache controls
        const flushCacheBtn = document.getElementById('flush-cache');
        if (flushCacheBtn) {
            flushCacheBtn.addEventListener('click', this.flushCache.bind(this));
        }

        const clearCacheBtn = document.getElementById('clear-cache');
        if (clearCacheBtn) {
            clearCacheBtn.addEventListener('click', this.clearCache.bind(this));
        }

        const flushDomainBtn = document.getElementById('flush-domain-btn');
        if (flushDomainBtn) {
            flushDomainBtn.addEventListener('click', this.flushDomainCache.bind(this));
        }

        // Search functionality
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchFilter = e.target.value.toLowerCase();
                this.filterQueries();
            });
        }

        // Auto-scroll toggle
        const autoScrollCheckbox = document.getElementById('auto-scroll');
        if (autoScrollCheckbox) {
            autoScrollCheckbox.addEventListener('change', (e) => {
                this.autoScroll = e.target.checked;
            });
        }

        // Clear logs button
        const clearLogsBtn = document.getElementById('clear-logs');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', this.clearQueries.bind(this));
        }

        // Handle domain input enter key
        const domainInput = document.getElementById('flush-domain');
        if (domainInput) {
            domainInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.flushDomainCache();
                }
            });
        }
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

        // Update cache stats
        if (data.cache) {
            this.updateElement('cache-hits', data.cache.cache_hits || 0);
            this.updateElement('cache-misses', data.cache.cache_misses || 0);
            
            const hitRatio = data.cache.hit_ratio || 0;
            this.updateElement('cache-hit-ratio', (hitRatio * 100).toFixed(1) + '%');
            
            this.updateElement('cache-memory', (data.cache.current_memory_mb || 0).toFixed(1) + ' MB');
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
        this.updateStats(data.dns, data.cache);
    }

    /**
     * Update statistics (called by WebSocket or API)
     */
    updateStats(dnsStats, cacheStats) {
        if (window.chartsManager) {
            window.chartsManager.updateCharts(dnsStats, cacheStats);
        }
    }

    /**
     * Add new DNS query to display
     */
    addDnsQuery(query) {
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

        // Update display
        this.renderQueries();
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

        // Render filtered queries
        filteredQueries.forEach(query => {
            const queryRow = this.createQueryRow(query);
            queriesList.appendChild(queryRow);
        });

        // Auto-scroll to bottom
        if (this.autoScroll && !this.searchFilter) {
            setTimeout(() => {
                queriesList.scrollTop = queriesList.scrollHeight;
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

        // Format cache status
        const cacheStatus = query.cache_hit ? 'HIT' : 'MISS';
        const cacheClass = query.cache_hit ? 'cache-hit' : 'cache-miss';

        row.innerHTML = `
            <div class="query-col timestamp-col">${timestamp}</div>
            <div class="query-col client-col">${query.client_ip || '-'}</div>
            <div class="query-col domain-col" title="${query.domain || '-'}">${query.domain || '-'}</div>
            <div class="query-col type-col">${query.query_type || '-'}</div>
            <div class="query-col response-col">
                <span class="response-code ${responseClass}">${query.response_code || '-'}</span>
            </div>
            <div class="query-col time-col">${query.response_time_ms || '-'}</div>
            <div class="query-col cache-col">
                <span class="${cacheClass}">${cacheStatus}</span>
            </div>
        `;

        return row;
    }

    /**
     * Filter queries based on search input
     */
    filterQueries() {
        this.renderQueries();
    }

    /**
     * Clear all queries
     */
    clearQueries() {
        this.queries = [];
        this.renderQueries();
        
        // Clear charts data
        if (window.chartsManager) {
            window.chartsManager.clearAllData();
        }

        this.showNotification('Query logs cleared', 'info');
    }

    /**
     * Flush cache
     */
    async flushCache() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/cache/flush`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.showNotification(`Cache flushed: ${data.entries_removed || 0} entries removed`, 'success');
                this.refreshData();
            } else {
                throw new Error('Failed to flush cache');
            }
        } catch (error) {
            console.error('Error flushing cache:', error);
            this.showNotification('Failed to flush cache', 'error');
        }
    }

    /**
     * Clear cache
     */
    async clearCache() {
        if (!confirm('Are you sure you want to clear the entire cache?')) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/cache/clear`, {
                method: 'DELETE'
            });

            if (response.ok) {
                const data = await response.json();
                this.showNotification(`Cache cleared: ${data.entries_removed || 0} entries removed`, 'success');
                this.refreshData();
            } else {
                throw new Error('Failed to clear cache');
            }
        } catch (error) {
            console.error('Error clearing cache:', error);
            this.showNotification('Failed to clear cache', 'error');
        }
    }

    /**
     * Flush domain-specific cache
     */
    async flushDomainCache() {
        const domainInput = document.getElementById('flush-domain');
        if (!domainInput) return;

        const domain = domainInput.value.trim();
        if (!domain) {
            this.showNotification('Please enter a domain name', 'warning');
            return;
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/cache/flush`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ domain: domain })
            });

            if (response.ok) {
                const data = await response.json();
                this.showNotification(`Domain cache flushed: ${data.entries_removed || 0} entries removed`, 'success');
                domainInput.value = '';
                this.refreshData();
            } else {
                throw new Error('Failed to flush domain cache');
            }
        } catch (error) {
            console.error('Error flushing domain cache:', error);
            this.showNotification('Failed to flush domain cache', 'error');
        }
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