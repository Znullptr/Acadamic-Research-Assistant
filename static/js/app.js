// Marked configuration
marked.setOptions({
    breaks: true,
    gfm: true,
    sanitize: false,
    smartLists: true,
    smartypants: false
});

// Application State
let currentRequestId = null;
let isProcessing = false;
let chatHistory = [];
let selectedFiles = [];

// DOM Elements
const chatInput = document.getElementById('chatInput');
const sendButton = document.getElementById('sendButton');
const loadingOverlay = document.getElementById('loadingOverlay');
const resultsSection = document.getElementById('resultsSection');
const heroSection = document.getElementById('heroSection');
const metricsGrid = document.getElementById('metricsGrid');
const reportSections = document.getElementById('reportSections');
const navItems = document.querySelectorAll('.nav-item');

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    adjustTextareaHeight();
    checkApiStatus();
    initializeApp();
});

// Event Listeners
function setupEventListeners() {
    // Send message on button click
    sendButton.addEventListener('click', handleSendMessage);

    // Send message on Enter (Shift+Enter for new line)
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
   
    // Auto-resize textarea
    chatInput.addEventListener('input', adjustTextareaHeight);

    // Navigation
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const page = this.dataset.page;
            switchPage(page);
            
            // Update active state
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');
        });
    });

    // Knowledge base upload documents
    const uploadBtn = document.getElementById('upload-docs-btn');
    if (uploadBtn) {
        uploadBtn.addEventListener('click', function() {
            document.getElementById('pdf-file-input').click();
        });
    }

    // File upload handler
    const fileInput = document.getElementById('pdf-file-input');
    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const files = Array.from(e.target.files);
            
            if (files.length === 0) return;
                            
            try {
                const formData = new FormData();
                files.forEach(file => {
                    formData.append('files', file);
                });
                
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    showAlert('success', result.message, 3000);
                    const processed_response = await fetch('/api/process_uploaded_files');
                    const processed_response_data = await processed_response.json();
                    if (processed_response.ok) {
                      showAlert('success', processed_response_data.message, 3000);
                    } else {
                      showAlert('error', processed_response_data.message, 3000);
                    }
                } else {
                    const errorMessage = result.errors && result.errors.length > 0 
                        ? `Upload failed: ${result.errors[0]}` 
                        : result.error || 'Upload failed';
                    showAlert('error', errorMessage, 4000);
                }
                
            } catch (error) {
                console.error('Network error:', error);
                showAlert('error', `Network error: ${error.message}`, 4000);
            }
            
            e.target.value = '';
        });
    }
}

// Switch between pages
function switchPage(pageName) {
    // Hide all pages
    document.querySelectorAll('.page-content').forEach(page => {
        page.style.display = 'none';
    });
    
    // Show selected page
    const targetPage = document.getElementById(`${pageName}-page`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }
    
    // Handle page-specific logic
    switch(pageName) {
        case 'knowledge':
            break;
        case 'analytics':
            // Load analytics
            loadStatistics();
            loadResearchTrends();
            break;
        case 'history':
            // Load history
            loadChatHistory();
            break;
        case 'research':
            // Research page is the default
            break;
    }
    
    console.log('Switching to page:', pageName);
}


// Auto-resize textarea
function adjustTextareaHeight() {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
}

// Check API Status
async function checkApiStatus() {
    try {
        const response = await fetch('/health');
        if (response.ok) {
            updateApiStatus('online', 'Online');
        } else {
            updateApiStatus('error', 'Offline');
        }
    } catch (error) {
        updateApiStatus('error', 'Offline');
        console.error('API status check failed:', error);
    }
}

// Update API Status Display
function updateApiStatus(status, text) {
    const statusIndicator = document.querySelector('.status-indicator span');
    const statusDot = document.querySelector('.status-dot');
    
    if (statusIndicator) statusIndicator.textContent = text;
    
    if (statusDot) {
        statusDot.className = 'status-dot';
        if (status === 'online') {
            statusDot.style.background = '#10b981';
        } else {
            statusDot.style.background = '#ef4444';
        }
    }
}

// Session Management Module
class SessionManager {
    constructor() {
        this.sessionId = null;
        this.sessionKey = 'chatSessionId';
        this.sessionExpiryKey = 'chatSessionExpiry';
        this.sessionDuration = 24 * 60 * 60 * 1000; // 24 hours
    }

    async initialize() {
        const storedSessionId = localStorage.getItem(this.sessionKey);
        const storedExpiry = localStorage.getItem(this.sessionExpiryKey);

        if (storedSessionId && storedExpiry) {
            const expiryTime = parseInt(storedExpiry);
            const now = Date.now();

            if (now < expiryTime) {
                if (await this.validateSession(storedSessionId)) {
                    this.sessionId = storedSessionId;
                    console.log('Existing session restored:', this.sessionId);
                    return this.sessionId;
                }
            }
        }

        return await this.createNewSession();
    }

    async validateSession(sessionId) {
        try {
            const response = await fetch('/api/session/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });

            if (response.ok) {
                const data = await response.json();
                return data.valid === true;
            }
            return false;
        } catch (error) {
            console.warn('Session validation failed:', error);
            return false;
        }
    }

    async createNewSession() {
        try {
            const response = await fetch('/api/session/start', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`Failed to create session: ${response.status}`);
            }

            const data = await response.json();
            this.sessionId = data.session_id;
            
            const expiryTime = Date.now() + this.sessionDuration;
            localStorage.setItem(this.sessionKey, this.sessionId);
            localStorage.setItem(this.sessionExpiryKey, expiryTime.toString());

            console.log('New session created:', this.sessionId);
            return this.sessionId;
        } catch (error) {
            console.error('Failed to create session:', error);
            throw error;
        }
    }

    async getSessionId() {
        if (!this.sessionId) {
            return await this.initialize();
        }
        return this.sessionId;
    }

    async startNewSession() {
        this.clearSession();
        return await this.createNewSession();
    }

    clearSession() {
        this.sessionId = null;
        localStorage.removeItem(this.sessionKey);
        localStorage.removeItem(this.sessionExpiryKey);
    }

    refreshSession() {
        if (this.sessionId) {
            const expiryTime = Date.now() + this.sessionDuration;
            localStorage.setItem(this.sessionExpiryKey, expiryTime.toString());
        }
    }

    shouldRefreshSession() {
        const storedExpiry = localStorage.getItem(this.sessionExpiryKey);
        if (!storedExpiry) return false;

        const expiryTime = parseInt(storedExpiry);
        const now = Date.now();
        const timeUntilExpiry = expiryTime - now;
        
        return timeUntilExpiry < (60 * 60 * 1000);
    }
}

// Initialize session manager
const sessionManager = new SessionManager();

// Handle message
async function handleSendMessage() {
    const message = chatInput.value.trim();
    if (!message || isProcessing) return;

    if (selectedFiles.length > 0) {
        await uploadFiles();
    }

    // Show loading state
    showLoading();
    setProcessingState(true);

    try {
        const sessionId = await sessionManager.getSessionId();

        if (sessionManager.shouldRefreshSession()) {
            sessionManager.refreshSession();
        }

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        if (!res.ok) {
            if (res.status === 401 || res.status === 403) {
                console.log('Session expired, creating new session');
                const newSessionId = await sessionManager.startNewSession();
                
                const retryRes = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: newSessionId,
                        message: message
                    })
                });

                if (!retryRes.ok) {
                    throw new Error(`API returned ${retryRes.status} on retry`);
                }

                const retryData = await retryRes.json();
                
                if (retryData.type === "research") {
                    await monitorResearchProgress(retryData.request_id);
                } else {
                    showSimpleResults(retryData.content || "No response from server.");
                }
                return;
            }
            
            throw new Error(`API returned ${res.status}`);
        }

        const data = await res.json();

        if (data.type === "research") {
            await monitorResearchProgress(data.request_id);
        } else {
            showSimpleResults(data.content || "No response from server.");
        }
        
    } catch (error) {
        console.error('Error processing message:', error);
        hideLoading();
        showSimpleResults('Sorry, I encountered an error processing your request. Please try again.');
    } finally {
        setProcessingState(false);
    }
}

// Monitor research progress
async function monitorResearchProgress(requestId) {
    const maxWaitTime = 300000; // 5 minutes
    const checkInterval = 2000; // 2 seconds
    let elapsedTime = 0;
    let lastProgress = '';

    // Update loading text to show progress monitoring
    updateLoadingText('Analyzing Research', 'Processing academic papers...');

    while (elapsedTime < maxWaitTime) {
        try {
            const response = await fetch(`api/research/${requestId}/status`);
            
            if (response.ok) {
                const statusData = await response.json();
                const currentStatus = statusData.status;
                const currentStep = statusData.current_step;
                const progress = statusData.progress;

                if (progress !== lastProgress) {
                    updateLoadingText('Analyzing Research', `${currentStep} (${progress}%)`);
                    lastProgress = progress;
                }

                if (currentStatus === 'completed') {
                    await displayResearchResults(requestId);
                    break;
                } else if (currentStatus === 'failed') {
                    hideLoading();
                    const errorMsg = statusData.error || 'Unknown error';
                    showSimpleResults(`Research failed: ${errorMsg}`);
                    break;
                }
            }

            await new Promise(resolve => setTimeout(resolve, checkInterval));
            elapsedTime += checkInterval;

        } catch (error) {
            console.error('Error checking status:', error);
            break;
        }
    }

    if (elapsedTime >= maxWaitTime) {
        hideLoading();
        showSimpleResults('Research is taking longer than expected. Please check back later or start a new search.');
    }
}

// Display research results
async function displayResearchResults(requestId) {
    try {
        const response = await fetch(`api/research/${requestId}/results`);
        
        if (response.ok) {
            const results = await response.json();
            hideLoading();
            showResearchResults(results);
        } else if (response.status === 400) {
            updateLoadingText('Analyzing Research', 'Still processing, please wait...');
        } else {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || 'Failed to get results');
        }
        
    } catch (error) {
        hideLoading();
        showSimpleResults(`Error displaying results: ${error.message}`);
    }
}

// Show loading state
function showLoading() {
    heroSection.classList.add('compact');
    loadingOverlay.classList.add('active');
    chatInput.value = '';
    adjustTextareaHeight();
}

// Hide loading state
function hideLoading() {
    loadingOverlay.classList.remove('active');
}

// Update loading text
function updateLoadingText(title, subtitle) {
    const loadingText = document.querySelector('.loading-text');
    const loadingSubtext = document.querySelector('.loading-subtext');
    
    if (loadingText) loadingText.textContent = title;
    if (loadingSubtext) loadingSubtext.textContent = subtitle;
}

// Show simple results (for non-research responses)
function showSimpleResults(content) {
    const sections = [
        {
            icon: 'fas fa-comment-alt',
            title: 'Response',
            items: [
                {
                    title: 'AI Response',
                    content: content
                }
            ]
        }
    ];

    populateMetrics([
        { value: '1', label: 'Response' },
        { value: 'N/A', label: 'Citations' },
        { value: 'N/A', label: 'Trends' },
        { value: 'N/A', label: 'Gaps' }
    ]);

    populateReportSections(sections);
    resultsSection.classList.add('visible');
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


// Show research results
function showResearchResults(results) {
    const synthesis = results.synthesis || {};
    const papers_found = results.papers_found || 0;
    const content_extracted = results.content_extracted || 0;
    const quality_score = results.quality_score || 0;

    // Calculate metrics
    const totalCitations = synthesis.citation_network?.citation_stats?.total_citations || 0;
    const keyFindingsCount = synthesis.key_findings ? synthesis.key_findings.length : 0;
    const researchGapsCount = synthesis.research_gaps ? synthesis.research_gaps.length : 0;

    // Populate metrics
    populateMetrics([
        { value: papers_found.toString(), label: 'Papers Found' },
        { value: content_extracted.toString(), label: 'Extracted Web Content' },
        { value: `${quality_score}/100`, label: 'Quality Score' },
        { value: formatNumber(totalCitations), label: 'Total Citations' },
        { value: keyFindingsCount.toString(), label: 'Key Findings' },
        { value: researchGapsCount.toString(), label: 'Research Gaps' }
    ]);

    // Prepare sections
    const sections = [];

    // Executive Summary
    if (synthesis.summary) {
        sections.push({
            icon: 'fas fa-file-alt',
            title: 'Executive Summary',
            items: [
                {
                    title: 'Research Summary',
                    content: synthesis.summary
                }
            ]
        });
    }

    // Key Findings
    if (synthesis.key_findings && synthesis.key_findings.length > 0) {
        sections.push({
            icon: 'fas fa-lightbulb',
            title: 'Key Findings',
            items: synthesis.key_findings.slice(0, 8).map((finding, index) => ({
                title: `Finding ${index + 1}`,
                content: `<strong>Finding:</strong> ${finding.finding || 'N/A'}<br><strong>Evidence Level:</strong> ${finding.evidence_level || 'N/A'}`
            }))
        });
    }

    // Research Gaps
    if (synthesis.research_gaps && synthesis.research_gaps.length > 0) {
        sections.push({
            icon: 'fas fa-search',
            title: 'Research Gaps & Opportunities',
            items: synthesis.research_gaps.slice(0, 5).map((gap, index) => ({
                title: `Gap ${index + 1}`,
                content: `<strong>Gap:</strong> ${gap.gap || 'N/A'}<br><strong>Significance:</strong> ${gap.significance || 'N/A'}<br><strong>Suggested Direction:</strong> ${gap.suggested_direction || 'N/A'}`
            }))
        });
    }

    // Methodology Trends
    if (synthesis.methodology_trends && synthesis.methodology_trends.length > 0) {
        sections.push({
            icon: 'fas fa-cogs',
            title: 'Methodology Trends',
            items: synthesis.methodology_trends.slice(1).map((trend) => {
                const colonIndex = trend.indexOf(':');
                if (colonIndex !== -1 && colonIndex > 0) {
                    const title = trend.substring(0, colonIndex).replace(/\*/g, '').trim();
                    const wrappedTitle = `**${title}**`;
                    
                    return {
                        title: marked.parse(wrappedTitle).replace(/<\/?p>/g, ''),
                        content: trend.substring(colonIndex + 3).trim()
                    };
                } 
            }).filter(item => item) 
        });
    }

    // Future Directions
    if (synthesis.future_directions && synthesis.future_directions.length > 0) {
        sections.push({
            icon: 'fas fa-rocket',
            title: 'Future Research Directions',
            items: synthesis.future_directions.slice(1).map((direction, index) => {
                const colonIndex = direction.indexOf(':');
                if (colonIndex !== -1 && colonIndex > 0) {
                    const title = direction.substring(0, colonIndex).replace(/\*/g, '').trim();
                    const wrappedTitle = `**${title}**`;
                    
                    return {
                        title: marked.parse(wrappedTitle).replace(/<\/?p>/g, ''),
                        content: direction.substring(colonIndex + 3).trim()
                    };
                } 
            }).filter(item => item) 
        });
    }

    
    // Top Cited Papers
    if (synthesis.citation_network?.highly_cited_papers && synthesis.citation_network.highly_cited_papers.length > 0) {
        const citation_data = synthesis.citation_network;
        let citedPapersHtml = `
            <div class="cited-papers">
                <h4>Top Cited Papers</h4>
                <div class="papers-chart">
                    ${citation_data.highly_cited_papers.slice(0, 10).map(paper => `
                        <div class="citation-bar">
                            <div class="paper-title">${(paper.title || 'Unknown Title').substring(0, 60)}...</div>
                            <div class="citation-count">${paper.citations || 0} citations</div>
                            <div class="citation-visual">
                                <div class="citation-fill" style="width: ${Math.min((paper.citations || 0) / (citation_data.citation_stats?.max_citations || 1) * 100, 100)}%"></div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        sections.push({
            icon: 'fas fa-star',
            title: 'Top Cited Papers',
            items: [
                {
                    title: 'Citation Analysis',
                    content: citedPapersHtml,
                    isHtml: true
                }
            ]
        });
    }

    // Timeline Analysis
    if (synthesis.timeline_insights && synthesis.timeline_insights.length > 0) {
        let timelineHtml = `
            <div class="timeline-insights">
                ${synthesis.timeline_insights.map(insight => `
                    <div class="timeline-item">
                        <strong>${insight.trend || 'N/A'}:</strong> ${marked.parse(insight.description || 'N/A')}
                    </div>
                `).join('')}
            </div>
        `;

        sections.push({
            icon: 'fas fa-calendar-alt',
            title: 'Temporal Trends',
            items: [
                {
                    title: 'Timeline Analysis',
                    content: timelineHtml,
                    isHtml: true
                }
            ]
        });
    }

    populateReportSections(sections);
    resultsSection.classList.add('visible');
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Populate metrics grid
function populateMetrics(metrics) {
    metricsGrid.innerHTML = metrics.map(metric => `
        <div class="metric-card">
            <div class="metric-value">${metric.value}</div>
            <div class="metric-label">${metric.label}</div>
        </div>
    `).join('');
}

// Populate report sections
function populateReportSections(sections) {
    reportSections.innerHTML = sections.map(section => `
        <div class="report-section">
            <div class="section-header" onclick="toggleSection(this)">
                <div class="section-title">
                    <div class="section-icon">
                        <i class="${section.icon}"></i>
                    </div>
                    ${section.title}
                </div>
                <i class="fas fa-chevron-down expand-icon"></i>
            </div>
            <div class="section-content">
                ${section.items.map(item => `
                    <div class="finding-item">
                        <div class="finding-title">${item.title}</div>
                        <div class="finding-content">${
                            item.isHtml ? item.content : marked.parse(item.content)
                        }</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');

    // Auto-expand first section
    setTimeout(() => {
        const firstSection = document.querySelector('.section-header');
        if (firstSection) {
            toggleSection(firstSection);
        }
    }, 100);
}

// Load research trends and display bar chart
async function loadResearchTrends() {
    const chartContainer = document.querySelector('.analytics-charts .chart-container');
    
    if (!chartContainer) return;
    
    // Show loading state
    const chartPlaceholder = chartContainer.querySelector('.chart-placeholder');
    if (chartPlaceholder) {
        chartPlaceholder.innerHTML = `
            <div class="loading-spinner-small"></div>
            <p>Loading research trends...</p>
        `;
    }
    
    try {
        const response = await fetch('/api/clusters');
        
        if (response.ok) {
            const data = await response.json();
            displayTrendsChart(data || []);
        } else {
            showChartError('Failed to load research trends');
        }
    } catch (error) {
        console.error('Research trends loading error:', error);
        showChartError('Connection error while loading trends');
    }
}

// Display the trends bar chart
function displayTrendsChart(trends) {
    const chartContainer = document.querySelector('.analytics-charts .chart-container');
    
    if (!chartContainer || !trends || trends.length === 0) {
        showChartError('No research trends data available');
        return;
    }
    
    // Calculate max value for scaling
    const maxValue = Math.max(...trends.map(t => t.size));
    
    // Generate chart HTML
    const chartHTML = `
        <h3 class="section-heading">
            <i class="fas fa-chart-bar"></i>
            Research Trends
        </h3>
        <div class="trends-chart">
            <div class="chart-header">
                <span class="chart-title">Top Research Topics</span>
                <span class="chart-subtitle">${trends.length} total trends identified</span>
            </div>
            <div class="chart-bars">
                ${trends.map((trend, index) => `
                    <div class="trend-bar-item">
                        <div class="trend-info">
                            <span class="trend-label" title="${trend.label}">${truncateText(trend.label, 40)}</span>
                            <span class="trend-value">${trend.size} papers</span>
                        </div>
                        <div class="trend-bar-container">
                            <div class="trend-bar" 
                                 style="width: ${(trend.size / maxValue) * 100}%; 
                                        animation-delay: ${index * 0.1}s;">
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
            <div class="chart-footer">
                <small>Showing top ${trends.length} research trends by paper count</small>
            </div>
        </div>
    `;
    
    chartContainer.innerHTML = chartHTML;
    
    // Animate bars
    setTimeout(() => {
        const bars = chartContainer.querySelectorAll('.trend-bar');
        bars.forEach(bar => {
            bar.style.opacity = '1';
            bar.style.transform = 'scaleX(1)';
        });
    }, 100);
}

// Show chart error state
function showChartError(message) {
    const chartContainer = document.querySelector('.analytics-charts .chart-container');
    
    if (chartContainer) {
        chartContainer.innerHTML = `
            <h3 class="section-heading">
                <i class="fas fa-chart-bar"></i>
                Research Trends
            </h3>
            <div class="chart-placeholder">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${message}</p>
            </div>
        `;
    }
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
}

// Toggle section function
function toggleSection(header) {
    const content = header.nextElementSibling;
    const isExpanded = content.classList.contains('expanded');
    
    // Close all sections first
    document.querySelectorAll('.section-content.expanded').forEach(section => {
        section.classList.remove('expanded');
        section.previousElementSibling.classList.remove('expanded');
    });
    
    // If this section wasn't expanded, expand it
    if (!isExpanded) {
        content.classList.add('expanded');
        header.classList.add('expanded');
        
        // Smooth scroll to section after expansion
        setTimeout(() => {
            header.scrollIntoView({
                behavior: 'smooth',
                block: 'nearest'
            });
        }, 200);
    }
}

// Set processing state
function setProcessingState(processing) {
    isProcessing = processing;
    sendButton.disabled = processing;
    chatInput.disabled = processing;
}

// Application initialization
async function initializeApp() {
    try {
        await sessionManager.initialize();
        
        setInterval(() => {
            if (sessionManager.shouldRefreshSession()) {
                sessionManager.refreshSession();
                console.log('Session refreshed');
            }
        }, 5 * 60 * 1000);

    } catch (error) {
        console.error('Failed to initialize app:', error);
    }
}

// Utility functions
function showAlert(type, message, duration = 3000) {
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    
    // Style the alert
    alert.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        z-index: 10000;
        max-width: 300px;
        word-wrap: break-word;
    `;
    
    if (type === 'success') {
        alert.style.backgroundColor = '#10b981';
    } else if (type === 'error') {
        alert.style.backgroundColor = '#ef4444';
    } else if (type === 'warning') {
        alert.style.backgroundColor = '#f59e0b';
    }
    
    document.body.appendChild(alert);
    
    // Remove after duration
    setTimeout(() => {
        if (alert.parentNode) {
            alert.parentNode.removeChild(alert);
        }
    }, duration);
}

// Load statistics for Analytics page
async function loadStatistics() {
    const statsGrid = document.getElementById('stats-grid');
    
    // Show loading state
    if (statsGrid) {
        statsGrid.innerHTML = `
            <div class="stat-card loading">
                <div class="loading-spinner-small"></div>
                <div class="stat-label">Loading Statistics...</div>
            </div>
        `;
    }
    
    try {
        const response = await fetch('/api/statistics');
        
        if (response.ok) {
            const data = await response.json();
            displayStatistics(data);
        } else {
            if (statsGrid) {
                statsGrid.innerHTML = `
                    <div class="stat-card error">
                        <div class="stat-icon">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="stat-title">Error Loading Statistics</div>
                        <div class="stat-value">---</div>
                        <div class="stat-description">Failed to load data from API</div>
                    </div>
                `;
            }
        }
    } catch (error) {
        console.error('Statistics loading error:', error);
        if (statsGrid) {
            statsGrid.innerHTML = `
                <div class="stat-card error">
                    <div class="stat-icon">
                        <i class="fas fa-wifi"></i>
                    </div>
                    <div class="stat-title">Connection Error</div>
                    <div class="stat-value">---</div>
                    <div class="stat-description">Unable to connect to the API</div>
                </div>
            `;
        }
    }
}

// Display statistics
function displayStatistics(data) {
    const statsGrid = document.getElementById('stats-grid');
    
    if (!statsGrid) return;
    
    const statsHtml = `
        <div class="stat-card">
            <div class="stat-icon">
                <i class="fas fa-file-alt"></i>
            </div>
            <div class="stat-title">Total Documents</div>
            <div class="stat-value">${data.total_documents || 0}</div>
            <div class="stat-description">Documents in knowledge base</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">
                <i class="fas fa-newspaper"></i>
            </div>
            <div class="stat-title">Unique Papers</div>
            <div class="stat-value">${data.unique_papers || 0}</div>
            <div class="stat-description">Academic papers processed</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">
                <i class="fas fa-users"></i>
            </div>
            <div class="stat-title">Authors</div>
            <div class="stat-value">${data.unique_authors || 0}</div>
            <div class="stat-description">Unique authors identified</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">
                <i class="fas fa-trophy"></i>
            </div>
            <div class="stat-title">Top Venue</div>
            <div class="stat-value">${data.top_venue || 'None'}</div>
            <div class="stat-description">Most published venue</div>
        </div>
    `;
    
    statsGrid.innerHTML = statsHtml;
}

// Load chat history for History page
function loadChatHistory() {
    const historyContainer = document.getElementById('history-container');
    
    if (!historyContainer) return;
    
    try {
        // Check if we have chat history data
        if (window.chatHistoryData) {
            const messages = window.chatHistoryData.messages || [];
            displayChatHistory(messages);
        } else if (chatHistory && chatHistory.length > 0) {
            displayChatHistory(chatHistory);
        } else {
            // Show empty state
            historyContainer.innerHTML = `
                <div class="history-empty-state">
                    <div class="empty-icon">
                        <i class="fas fa-history"></i>
                    </div>
                    <h3>No Chat History</h3>
                    <p>Your research conversations will appear here</p>
                </div>
            `;
        }
    } catch (error) {
        console.warn('Failed to load chat history:', error);
        historyContainer.innerHTML = `
            <div class="history-error">
                <div class="error-icon">
                    <i class="fas fa-exclamation-triangle"></i>
                </div>
                <h3>Error Loading History</h3>
                <p>Failed to load chat history</p>
            </div>
        `;
    }
}

// Display chat history
function displayChatHistory(messages) {
    const historyContainer = document.getElementById('history-container');
    
    if (!historyContainer || !messages || messages.length === 0) {
        historyContainer.innerHTML = `
            <div class="history-empty-state">
                <div class="empty-icon">
                    <i class="fas fa-history"></i>
                </div>
                <h3>No Chat History</h3>
                <p>Your research conversations will appear here</p>
            </div>
        `;
        return;
    }
    
// Group messages by date
const groupedMessages = groupMessagesByDate(messages);

let historyHtml = '';

Object.keys(groupedMessages).forEach(date => {
    historyHtml += `
        <div class="history-group">
            <div class="history-date">
                <i class="fas fa-calendar-alt"></i>
                ${date}
            </div>
            <div class="history-messages">
    `;
    
    groupedMessages[date].forEach(msg => {
        historyHtml += `
            <div class="history-message ${msg.sender}">
                <div class="history-message-avatar">
                    <i class="fas fa-${msg.sender === 'user' ? 'user' : 'robot'}"></i>
                </div>
                <div class="history-message-content">
                    <div class="history-message-bubble">
                        ${msg.isHtml ? msg.content : escapeHtml(msg.content)}
                    </div>
                    <div class="history-message-time">
                        ${new Date(msg.timestamp).toLocaleTimeString()}
                    </div>
                </div>
            </div>
        `;
    });
    
    historyHtml += `
            </div>
        </div>
    `;
});

historyContainer.innerHTML = historyHtml;
}

// --- Helper functions ---
function groupMessagesByDate(messages) {
    const groups = {};
    
    messages.forEach(message => {
        const date = new Date(message.timestamp).toDateString();
        if (!groups[date]) {
            groups[date] = [];
        }
        groups[date].push(message);
    });
    
    return groups;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatNumber(num) {
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

// Periodic API status check
setInterval(checkApiStatus, 60000);

// Make toggleSection available globally
window.toggleSection = toggleSection;