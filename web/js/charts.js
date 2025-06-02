/**
 * DNS Dashboard Charts Manager
 * 
 * Manages Chart.js instances for DNS server statistics visualization
 */

class ChartsManager {
    constructor() {
        this.charts = {};
        this.theme = 'light';
        
        // Data storage for charts
        this.queryTypesData = {};
        this.responseTimeData = [];
        this.maxDataPoints = 50;
        
        // Listen for theme changes
        document.addEventListener('themeChanged', (e) => {
            this.theme = e.detail.isDark ? 'dark' : 'light';
            this.updateChartColors();
        });
    }

    /**
     * Initialize all charts
     */
    init() {
        this.initializeQueryTypesChart();
        this.initializeResponseTimeChart();
        
        console.log('✅ Charts Manager: All charts initialized');
    }

    /**
     * Get colors based on current theme
     */
    getColors() {
        const isDark = this.theme === 'dark';
        
        return {
            primary: isDark ? '#60a5fa' : '#3b82f6',
            secondary: isDark ? '#34d399' : '#10b981',
            accent: isDark ? '#fbbf24' : '#f59e0b',
            success: isDark ? '#34d399' : '#10b981',
            warning: isDark ? '#fbbf24' : '#f59e0b',
            error: isDark ? '#f87171' : '#ef4444',
            text: isDark ? '#e5e7eb' : '#374151',
            grid: isDark ? '#374151' : '#e5e7eb',
            background: isDark ? '#1f2937' : '#ffffff'
        };
    }

    /**
     * Initialize query types pie chart
     */
    initializeQueryTypesChart() {
        const canvas = document.getElementById('query-types-chart');
        if (!canvas) {
            console.warn('Query types chart canvas not found');
            return;
        }

        const ctx = canvas.getContext('2d');
        const colors = this.getColors();

        this.charts.queryTypes = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'Other'],
                datasets: [{
                    data: [0, 0, 0, 0, 0, 0],
                    backgroundColor: [
                        colors.primary,
                        colors.secondary,
                        colors.accent,
                        colors.warning,
                        colors.error,
                        colors.text
                    ],
                    borderWidth: 2,
                    borderColor: colors.background
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: colors.text,
                            usePointStyle: true,
                            padding: 20
                        }
                    },
                    tooltip: {
                        backgroundColor: colors.background,
                        titleColor: colors.text,
                        bodyColor: colors.text,
                        borderColor: colors.grid,
                        borderWidth: 1
                    }
                }
            }
        });
    }

    /**
     * Initialize response time line chart
     */
    initializeResponseTimeChart() {
        const canvas = document.getElementById('response-time-chart');
        if (!canvas) {
            console.warn('Response time chart canvas not found');
            return;
        }

        const ctx = canvas.getContext('2d');
        const colors = this.getColors();

        this.charts.responseTime = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: colors.primary,
                    backgroundColor: colors.primary + '20',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: colors.background,
                        titleColor: colors.text,
                        bodyColor: colors.text,
                        borderColor: colors.grid,
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        display: true,
                        grid: {
                            color: colors.grid
                        },
                        ticks: {
                            color: colors.text,
                            maxTicksLimit: 10
                        }
                    },
                    y: {
                        display: true,
                        beginAtZero: true,
                        grid: {
                            color: colors.grid
                        },
                        ticks: {
                            color: colors.text,
                            callback: function(value) {
                                return value + 'ms';
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Update charts with new data
     */
    updateCharts(dnsStats) {
        if (dnsStats) {
            this.updateQueryTypesChart(dnsStats);
            this.updateResponseTimeChart(dnsStats);
        }
    }

    /**
     * Update query types chart with new data
     */
    updateQueryTypesChart(dnsStats) {
        if (!this.charts.queryTypes) return;

        // For now, we'll use placeholder data since we don't have detailed query type stats
        // In a real implementation, you'd track these stats in the DNS server
        const data = [
            dnsStats.total_queries * 0.7,  // A records (70%)
            dnsStats.total_queries * 0.15, // AAAA records (15%)
            dnsStats.total_queries * 0.08, // CNAME records (8%)
            dnsStats.total_queries * 0.04, // MX records (4%)
            dnsStats.total_queries * 0.02, // TXT records (2%)
            dnsStats.total_queries * 0.01  // Other (1%)
        ];

        this.charts.queryTypes.data.datasets[0].data = data;
        this.charts.queryTypes.update('none');
    }

    /**
     * Update response time chart with new data point
     */
    updateResponseTimeChart(dnsStats) {
        if (!this.charts.responseTime) return;

        // Add new data point with current timestamp
        const now = new Date().toLocaleTimeString();
        const avgResponseTime = dnsStats.avg_response_time_ms || 0;

        this.responseTimeData.push({
            time: now,
            value: avgResponseTime
        });

        // Limit data points
        if (this.responseTimeData.length > this.maxDataPoints) {
            this.responseTimeData.shift();
        }

        // Update chart
        this.charts.responseTime.data.labels = this.responseTimeData.map(d => d.time);
        this.charts.responseTime.data.datasets[0].data = this.responseTimeData.map(d => d.value);
        this.charts.responseTime.update('none');
    }

    /**
     * Add new DNS query data point for real-time updates
     */
    addDnsQuery(query) {
        // Update query types data
        const queryType = query.query_type || 'Other';
        this.queryTypesData[queryType] = (this.queryTypesData[queryType] || 0) + 1;

        // Update response time data if we have timing information
        if (query.response_time_ms) {
            const now = new Date().toLocaleTimeString();
            this.responseTimeData.push({
                time: now,
                value: parseFloat(query.response_time_ms)
            });

            // Limit data points
            if (this.responseTimeData.length > this.maxDataPoints) {
                this.responseTimeData.shift();
            }

            // Update response time chart
            if (this.charts.responseTime) {
                this.charts.responseTime.data.labels = this.responseTimeData.map(d => d.time);
                this.charts.responseTime.data.datasets[0].data = this.responseTimeData.map(d => d.value);
                this.charts.responseTime.update('none');
            }
        }

        // Update query types chart
        if (this.charts.queryTypes) {
            const knownTypes = ['A', 'AAAA', 'CNAME', 'MX', 'TXT'];
            const data = knownTypes.map(type => this.queryTypesData[type] || 0);
            
            // Add "Other" category
            const otherCount = Object.keys(this.queryTypesData)
                .filter(type => !knownTypes.includes(type))
                .reduce((sum, type) => sum + this.queryTypesData[type], 0);
            data.push(otherCount);

            this.charts.queryTypes.data.datasets[0].data = data;
            this.charts.queryTypes.update('none');
        }
    }

    /**
     * Update chart colors when theme changes
     */
    updateChartColors() {
        const colors = this.getColors();

        // Update all charts with new colors
        Object.values(this.charts).forEach(chart => {
            if (chart.options.plugins?.legend?.labels) {
                chart.options.plugins.legend.labels.color = colors.text;
            }
            
            if (chart.options.plugins?.tooltip) {
                chart.options.plugins.tooltip.backgroundColor = colors.background;
                chart.options.plugins.tooltip.titleColor = colors.text;
                chart.options.plugins.tooltip.bodyColor = colors.text;
                chart.options.plugins.tooltip.borderColor = colors.grid;
            }

            if (chart.options.scales) {
                Object.values(chart.options.scales).forEach(scale => {
                    if (scale.grid) {
                        scale.grid.color = colors.grid;
                    }
                    if (scale.ticks) {
                        scale.ticks.color = colors.text;
                    }
                });
            }

            chart.update('none');
        });
    }

    /**
     * Clear all chart data
     */
    clearAllData() {
        this.queryTypesData = {};
        this.responseTimeData = [];

        // Reset chart data
        if (this.charts.queryTypes) {
            this.charts.queryTypes.data.datasets[0].data = [0, 0, 0, 0, 0, 0];
            this.charts.queryTypes.update('none');
        }

        if (this.charts.responseTime) {
            this.charts.responseTime.data.labels = [];
            this.charts.responseTime.data.datasets[0].data = [];
            this.charts.responseTime.update('none');
        }
    }

    /**
     * Destroy all charts
     */
    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
    }
}

// Create global charts manager instance
window.chartsManager = new ChartsManager();

// Initialize charts when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.chartsManager.init();
});
