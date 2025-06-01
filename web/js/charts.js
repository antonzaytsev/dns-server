/**
 * Charts Manager for DNS Server Dashboard
 * 
 * Manages Chart.js visualizations for DNS server statistics,
 * including query types, cache performance, and response times.
 */

class ChartsManager {
    constructor() {
        this.charts = {};
        this.chartColors = {
            primary: '#007bff',
            success: '#28a745',
            danger: '#dc3545',
            warning: '#ffc107',
            info: '#17a2b8',
            accent: '#6f42c1',
            secondary: '#6c757d'
        };

        // Data storage for time series
        this.responseTimeData = [];
        this.maxDataPoints = 50;
        
        // Query type tracking
        this.queryTypes = {};
        
        this.isDarkMode = false;
    }

    /**
     * Initialize all charts
     */
    init() {
        this.checkTheme();
        this.initQueryTypesChart();
        this.initCacheRatioChart();
        this.initResponseTimeChart();
        
        // Listen for theme changes
        document.addEventListener('themeChanged', (e) => {
            this.isDarkMode = e.detail.isDark;
            this.updateChartsTheme();
        });
    }

    /**
     * Check current theme
     */
    checkTheme() {
        this.isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    }

    /**
     * Get theme-appropriate colors
     */
    getThemeColors() {
        if (this.isDarkMode) {
            return {
                text: '#ffffff',
                grid: '#404040',
                background: 'rgba(255, 255, 255, 0.1)'
            };
        } else {
            return {
                text: '#2c3e50',
                grid: '#dee2e6',
                background: 'rgba(0, 0, 0, 0.05)'
            };
        }
    }

    /**
     * Initialize Query Types Distribution Chart
     */
    initQueryTypesChart() {
        const ctx = document.getElementById('query-types-chart');
        if (!ctx) return;

        const themeColors = this.getThemeColors();

        this.charts.queryTypes = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'PTR'],
                datasets: [{
                    data: [0, 0, 0, 0, 0, 0, 0],
                    backgroundColor: [
                        this.chartColors.primary,
                        this.chartColors.success,
                        this.chartColors.warning,
                        this.chartColors.danger,
                        this.chartColors.info,
                        this.chartColors.accent,
                        this.chartColors.secondary
                    ],
                    borderWidth: 2,
                    borderColor: themeColors.background
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: themeColors.text,
                            padding: 20,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label;
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                },
                animation: {
                    animateRotate: true,
                    duration: 1000
                }
            }
        });
    }

    /**
     * Initialize Cache Hit/Miss Ratio Chart
     */
    initCacheRatioChart() {
        const ctx = document.getElementById('cache-ratio-chart');
        if (!ctx) return;

        const themeColors = this.getThemeColors();

        this.charts.cacheRatio = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Cache Hits', 'Cache Misses'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: [
                        this.chartColors.success,
                        this.chartColors.danger
                    ],
                    borderWidth: 2,
                    borderColor: themeColors.background
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: themeColors.text,
                            padding: 20,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label;
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                },
                animation: {
                    animateRotate: true,
                    duration: 1000
                }
            }
        });
    }

    /**
     * Initialize Response Time Trend Chart
     */
    initResponseTimeChart() {
        const ctx = document.getElementById('response-time-chart');
        if (!ctx) return;

        const themeColors = this.getThemeColors();

        this.charts.responseTime = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: this.chartColors.primary,
                    backgroundColor: this.chartColors.primary + '20',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: this.chartColors.primary,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
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
                        labels: {
                            color: themeColors.text
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} ms`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Time',
                            color: themeColors.text
                        },
                        ticks: {
                            color: themeColors.text
                        },
                        grid: {
                            color: themeColors.grid
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Response Time (ms)',
                            color: themeColors.text
                        },
                        ticks: {
                            color: themeColors.text,
                            callback: function(value) {
                                return value.toFixed(0) + ' ms';
                            }
                        },
                        grid: {
                            color: themeColors.grid
                        },
                        beginAtZero: true
                    }
                },
                animation: {
                    duration: 750,
                    easing: 'easeInOutQuart'
                }
            }
        });
    }

    /**
     * Update query types chart with new data
     */
    updateQueryTypesChart(dnsStats) {
        if (!this.charts.queryTypes || !dnsStats) return;

        // Extract query type data from DNS stats
        // This assumes the DNS stats include query type breakdown
        const chartData = [
            dnsStats.query_types?.A || 0,
            dnsStats.query_types?.AAAA || 0,
            dnsStats.query_types?.CNAME || 0,
            dnsStats.query_types?.MX || 0,
            dnsStats.query_types?.TXT || 0,
            dnsStats.query_types?.NS || 0,
            dnsStats.query_types?.PTR || 0
        ];

        this.charts.queryTypes.data.datasets[0].data = chartData;
        this.charts.queryTypes.update('none'); // Update without animation for real-time feel
    }

    /**
     * Update cache ratio chart with new data
     */
    updateCacheRatioChart(cacheStats) {
        if (!this.charts.cacheRatio || !cacheStats) return;

        const hits = cacheStats.cache_hits || 0;
        const misses = cacheStats.cache_misses || 0;

        this.charts.cacheRatio.data.datasets[0].data = [hits, misses];
        this.charts.cacheRatio.update('none');
    }

    /**
     * Update response time chart with new data point
     */
    updateResponseTimeChart(avgResponseTime) {
        if (!this.charts.responseTime || avgResponseTime === undefined) return;

        const now = new Date();
        const timeLabel = now.toLocaleTimeString();

        // Add new data point
        this.responseTimeData.push({
            time: timeLabel,
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
     * Add a new DNS query to statistics
     */
    addDnsQuery(query) {
        if (!query) return;

        // Track query types
        const queryType = query.query_type || 'UNKNOWN';
        this.queryTypes[queryType] = (this.queryTypes[queryType] || 0) + 1;

        // Update response time if available
        if (query.response_time_ms !== undefined) {
            this.updateResponseTimeChart(query.response_time_ms);
        }
    }

    /**
     * Update all charts with new stats
     */
    updateCharts(dnsStats, cacheStats) {
        this.updateQueryTypesChart(dnsStats);
        this.updateCacheRatioChart(cacheStats);
        
        if (dnsStats && dnsStats.average_response_time !== undefined) {
            this.updateResponseTimeChart(dnsStats.average_response_time);
        }
    }

    /**
     * Update charts theme colors
     */
    updateChartsTheme() {
        const themeColors = this.getThemeColors();

        Object.values(this.charts).forEach(chart => {
            if (chart.options.plugins.legend) {
                chart.options.plugins.legend.labels.color = themeColors.text;
            }

            if (chart.options.scales) {
                Object.values(chart.options.scales).forEach(scale => {
                    if (scale.title) {
                        scale.title.color = themeColors.text;
                    }
                    if (scale.ticks) {
                        scale.ticks.color = themeColors.text;
                    }
                    if (scale.grid) {
                        scale.grid.color = themeColors.grid;
                    }
                });
            }

            chart.update('none');
        });
    }

    /**
     * Resize charts (useful for responsive design)
     */
    resizeCharts() {
        Object.values(this.charts).forEach(chart => {
            chart.resize();
        });
    }

    /**
     * Destroy all charts
     */
    destroy() {
        Object.values(this.charts).forEach(chart => {
            chart.destroy();
        });
        this.charts = {};
    }

    /**
     * Get chart data for export
     */
    getChartData(chartName) {
        const chart = this.charts[chartName];
        if (!chart) return null;

        return {
            labels: chart.data.labels,
            datasets: chart.data.datasets.map(dataset => ({
                label: dataset.label,
                data: [...dataset.data]
            }))
        };
    }

    /**
     * Clear all chart data
     */
    clearAllData() {
        // Clear response time data
        this.responseTimeData = [];

        // Clear query types
        this.queryTypes = {};

        // Reset all charts
        Object.values(this.charts).forEach(chart => {
            if (chart.data.datasets) {
                chart.data.datasets.forEach(dataset => {
                    dataset.data = Array(dataset.data.length).fill(0);
                });
            }
            if (chart.data.labels) {
                chart.data.labels = [];
            }
            chart.update();
        });
    }

    /**
     * Set chart animation duration
     */
    setAnimationDuration(duration) {
        Object.values(this.charts).forEach(chart => {
            if (chart.options.animation) {
                chart.options.animation.duration = duration;
            }
        });
    }

    /**
     * Export chart as image
     */
    exportChart(chartName, format = 'png') {
        const chart = this.charts[chartName];
        if (!chart) return null;

        return chart.toBase64Image(format);
    }

    /**
     * Get query type statistics
     */
    getQueryTypeStats() {
        return { ...this.queryTypes };
    }

    /**
     * Get response time statistics
     */
    getResponseTimeStats() {
        if (this.responseTimeData.length === 0) {
            return { min: 0, max: 0, avg: 0, latest: 0 };
        }

        const values = this.responseTimeData.map(d => d.value);
        return {
            min: Math.min(...values),
            max: Math.max(...values),
            avg: values.reduce((a, b) => a + b, 0) / values.length,
            latest: values[values.length - 1]
        };
    }
}

// Create global charts manager instance
window.chartsManager = new ChartsManager();

// Initialize charts when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait a bit for Chart.js to be fully loaded
    setTimeout(() => {
        window.chartsManager.init();
    }, 100);

    // Handle window resize
    window.addEventListener('resize', () => {
        setTimeout(() => {
            window.chartsManager.resizeCharts();
        }, 100);
    });
}); 