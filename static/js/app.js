
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
        const chatMessages = document.getElementById('chat-messages');
        const chatInput = document.getElementById('chat-input');
        const sendButton = document.getElementById('send-btn');
        const navItems = document.querySelectorAll('.nav-item');
        const pages = document.querySelectorAll('.page');
        const apiStatusDot = document.getElementById('api-status-dot');
        const apiStatusText = document.getElementById('api-status-text');

        // Initialize Application
        document.addEventListener('DOMContentLoaded', function() {
            setupEventListeners();
            adjustTextareaHeight();
            checkApiStatus();
            loadChatHistory();
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
            // Knowldge base upload documents
            document.getElementById('upload-docs-btn').addEventListener('click', function() {
                document.getElementById('pdf-file-input').click();
            });

            // File upload handler
            document.getElementById('pdf-file-input').addEventListener('change', async function(e) {
                const files = Array.from(e.target.files);
                
                if (files.length === 0) return;
                                
                try {
                    // Create FormData and append all files at once
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
                        // Full success (status 200)
                        showAlert('success', result.message, 3000);
                        const processed_response = await fetch('/api/process_uploaded_files');
                        const processed_response_data = await processed_response.json();
                        if (processed_response.ok) {
                          showAlert('success', processed_response_data.message, 3000);
                        }
                        else {
                          showAlert('error', processed_response_data.message, 3000);
                        }
                    
                    } else {
                        // Failure (status 400)
                        const errorMessage = result.errors && result.errors.length > 0 
                            ? `Upload failed: ${result.errors[0]}` 
                            : result.error || 'Upload failed';
                        showAlert('error', errorMessage, 4000);
                        if (result.errors) {
                            console.error('Upload errors:', result.errors);
                        }
                    }
                    
                } catch (error) {
                    console.error('Network error:', error);
                    showAlert('error', `Network error: ${error.message}`, 4000);
                }
                
                // Clear the input
                e.target.value = '';
            });


            // Knowledge search
            document.getElementById('knowledge-search-btn').addEventListener('click', performKnowledgeSearch);
            document.getElementById('knowledge-search-input').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    performKnowledgeSearch();
                }
            });
        }

        // Switch between pages
        function switchPage(pageName) {
            pages.forEach(page => page.classList.remove('active'));
            const targetPage = document.getElementById(`${pageName}-page`);
            if (targetPage) {
                targetPage.classList.add('active');
                
                // Load page-specific data
                if (pageName === 'statistics') {
                    loadStatistics();
                } else if (pageName === 'history') {
                    loadHistoryPage();
                }
            }
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
                    const data = await response.json();
                    updateApiStatus('online', 'API Online');
                } else {
                    updateApiStatus('warning', 'API Issues');
                }
            } catch (error) {
                updateApiStatus('error', 'API Offline');
                console.error('API status check failed:', error);
            }
        }

        // Update API Status Display
        function updateApiStatus(status, text) {
            apiStatusText.textContent = text;
            const settingsStatus = document.getElementById('settings-api-status');
            if (settingsStatus) {
                settingsStatus.textContent = text;
            }

            apiStatusDot.className = 'status-dot';
            
            if (status === 'online') {
                apiStatusDot.style.background = 'var(--success)';
            } else if (status === 'warning') {
                apiStatusDot.style.background = 'var(--warning)';
            } else {
                apiStatusDot.style.background = 'var(--error)';
            }
        }

        // Session Management Module
        class SessionManager {
            constructor() {
                this.sessionId = null;
                this.sessionKey = 'chatSessionId';
                this.sessionExpiryKey = 'chatSessionExpiry';
                this.sessionDuration = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
            }

            // Initialize session on app start
            async initialize() {
                const storedSessionId = localStorage.getItem(this.sessionKey);
                const storedExpiry = localStorage.getItem(this.sessionExpiryKey);

                if (storedSessionId && storedExpiry) {
                    const expiryTime = parseInt(storedExpiry);
                    const now = Date.now();

                    // Check if session is still valid
                    if (now < expiryTime) {
                        // Validate session with server
                        if (await this.validateSession(storedSessionId)) {
                            this.sessionId = storedSessionId;
                            console.log('Existing session restored:', this.sessionId);
                            return this.sessionId;
                        }
                    }
                }

                // Create new session if none exists or expired
                return await this.createNewSession();
            }

            // Validate session with server
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

            // Create new session
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
                    
                    // Store session with expiry
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

            // Get current session ID
            async getSessionId() {
                if (!this.sessionId) {
                    return await this.initialize();
                }
                return this.sessionId;
            }

            // Start new session (for manual reset)
            async startNewSession() {
                this.clearSession();
                return await this.createNewSession();
            }

            // Clear session data
            clearSession() {
                this.sessionId = null;
                localStorage.removeItem(this.sessionKey);
                localStorage.removeItem(this.sessionExpiryKey);
            }

            // Refresh session expiry
            refreshSession() {
                if (this.sessionId) {
                    const expiryTime = Date.now() + this.sessionDuration;
                    localStorage.setItem(this.sessionExpiryKey, expiryTime.toString());
                }
            }

            // Check if session needs refresh (call periodically)
            shouldRefreshSession() {
                const storedExpiry = localStorage.getItem(this.sessionExpiryKey);
                if (!storedExpiry) return false;

                const expiryTime = parseInt(storedExpiry);
                const now = Date.now();
                const timeUntilExpiry = expiryTime - now;
                
                // Refresh if less than 1 hour remaining
                return timeUntilExpiry < (60 * 60 * 1000);
            }
        }

        // Initialize session manager
        const sessionManager = new SessionManager();

        // handle message
        async function handleSendMessage() {
            const message = chatInput.value.trim();
            if (!message || isProcessing) return;

            if (selectedFiles.length > 0) {
                await uploadFiles();
            }

            // Add user message to chat
            addMessage('user', message);
            chatInput.value = '';
            adjustTextareaHeight();

            // Show typing indicator
            showTypingIndicator();
            setProcessingState(true);

            try {
                // Get session ID with automatic handling
                const sessionId = await sessionManager.getSessionId();

                // Refresh session if needed
                if (sessionManager.shouldRefreshSession()) {
                    sessionManager.refreshSession();
                }

                // Call the /api/chat endpoint
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
                    // Handle session expiry specifically
                    if (res.status === 401 || res.status === 403) {
                        console.log('Session expired, creating new session');
                        const newSessionId = await sessionManager.startNewSession();
                        
                        // Retry with new session
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
                        addMessage('assistant', retryData.content || "No response from server.");

                        if (retryData.type === "research") {
                            monitorResearchProgress(retryData.request_id);
                        }
                        return;
                    }
                    
                    throw new Error(`API returned ${res.status}`);
                }

                const data = await res.json();

                // Display the assistant's response
                addMessage('assistant', data.content || "No response from server.");

                if (data.type === "research") {
                    monitorResearchProgress(data.request_id);
                }
                
            } catch (error) {
                console.error('Error processing message:', error);
                addMessage('assistant', 'Sorry, I encountered an error processing your request. Please try again.');
            } finally {
                hideTypingIndicator();
                setProcessingState(false);
            }
        }

        // Application initialization
        async function initializeApp() {
            try {
                // Initialize session on app start
                await sessionManager.initialize();
                
                // Set up periodic session refresh check (every 5 minutes)
                setInterval(() => {
                    if (sessionManager.shouldRefreshSession()) {
                        sessionManager.refreshSession();
                        console.log('Session refreshed');
                    }
                }, 5 * 60 * 1000);

            } catch (error) {
                console.error('Failed to initialize app:', error);
                // Handle initialization failure
            }
        }

        // Utility functions for manual session management
        function startNewChatSession() {
            return sessionManager.startNewSession();
        }

        function clearChatSession() {
            sessionManager.clearSession();
        }


        document.addEventListener('DOMContentLoaded', initializeApp);


        // Add message to chat
        function addMessage(sender, content, isHtml = false, messageId = null) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}`;
            
            // Add ID if provided for future updates
            if (messageId) {
                messageDiv.id = messageId;
            }
            
            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.innerHTML = sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
            
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            
            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            
            if (isHtml) {
                bubble.innerHTML = content;
            } else {
                bubble.textContent = content;
            }
            
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            timeDiv.textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            messageContent.appendChild(bubble);
            messageContent.appendChild(timeDiv);
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(messageContent);
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Save to history
            chatHistory.push({
                sender: sender,
                content: content,
                timestamp: new Date().toISOString(),
                isHtml: isHtml
            });
            saveChatHistory();
        }

        // Monitor research progress
        async function monitorResearchProgress(requestId) {
            const maxWaitTime = 300000; // 5 minutes
            const checkInterval = 1000; // 5 seconds
            let elapsedTime = 0;
            let lastProgress = '';

            while (elapsedTime < maxWaitTime) {
                try {
                    const response = await fetch(`api/research/${requestId}/status`);
                    
                    if (response.ok) {
                        const statusData = await response.json();
                        console.log(statusData)
                        const currentStatus = statusData.status;
                        const currentStep = statusData.current_step;
                        const progress = statusData.progress;

                        if (progress !== lastProgress) {
                            updateProgressMessage(progress, currentStatus, currentStep);
                            lastProgress = progress;
                        }

                        if (currentStatus === 'completed') {
                            // Remove progress message before showing results
                            const progressMessage = document.getElementById('progress-message');
                            if (progressMessage) {
                                progressMessage.remove();
                            }
                            await displayResearchResults(requestId);
                            break;
                        } else if (currentStatus === 'failed') {
                            // Remove progress message before showing error
                            const progressMessage = document.getElementById('progress-message');
                            if (progressMessage) {
                                progressMessage.remove();
                            }
                            const errorMsg = statusData.error || 'Unknown error';
                            addMessage('assistant', `Research failed: ${errorMsg}`);
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
                // Remove progress message before showing timeout
                const progressMessage = document.getElementById('progress-message');
                if (progressMessage) {
                    progressMessage.remove();
                }
                addMessage('assistant', '⏰ Research is taking longer than expected. Please check back later or start a new search.');
            }
        }
        // Update progress message
        function updateProgressMessage(progress, status, currentStep) {
            const progressHtml = `
                <p>🔄 ${status === 'completed' ? 'Completed' : 'Processing'}: ${currentStep}</p>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <p style="font-size: 0.875rem; color: var(--text-muted);">Progress: ${progress}%</p>
            `;
            
            // Check if progress message already exists
            let progressMessage = document.getElementById('progress-message');
            
            if (progressMessage) {
                // Update existing message
                const bubble = progressMessage.querySelector('.message-bubble');
                bubble.innerHTML = progressHtml;
            } else {
                // Create new progress message with ID
                addMessage('assistant', progressHtml, true, 'progress-message');
            }
        }

        // Display research results
        async function displayResearchResults(requestId) {
            try {
                const response = await fetch(`api/research/${requestId}/results`);
                
                if (response.ok) {
                    const results = await response.json();
                    
                    // Create comprehensive results message
                    const resultsHtml = createResearchResultsHTML(results);
                    addMessage('assistant', resultsHtml, true);
                    
                } else if (response.status === 400) {
                    addMessage('assistant', '⏳ Research is still processing. Please wait...');
                } else {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Failed to get results');
                }
                
            } catch (error) {
                addMessage('assistant', `❌ Error displaying results: ${error.message}`);
            }
        }

        // Create research results HTML
        function createResearchResultsHTML(results) {
            const synthesis = results.synthesis || {};
            const papers_found = results.papers_found || 0;
            const content_extracted = results.content_extracted || 0;
            const quality_score = results.quality_score || 0;
            const status = results.status || 'completed';

            // Helper function to create expandable sections
            function createExpandableSection(title, content, isExpanded = false) {
                const id = `section-${Math.random().toString(36).substr(2, 9)}`;
                return `
                    <div class="expandable-section">
                        <div class="section-header" onclick="toggleSection('${id}')">
                            <i class="fas fa-chevron-${isExpanded ? 'down' : 'right'}" id="${id}-icon"></i>
                            <span>${title}</span>
                        </div>
                        <div class="section-content ${isExpanded ? 'expanded' : ''}" id="${id}">
                            ${content}
                        </div>
                    </div>
                `;
            }

            let html = `
                <div class="research-results">
                    <h3>📊 Research Analysis Complete</h3>
                    <br>
                    <!-- Overview Metrics -->
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <div class="metric-value">${papers_found}</div>
                            <div class="metric-label">Local Papers Found</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${content_extracted}</div>
                            <div class="metric-label">Web Content Extracted</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${quality_score}/100</div>
                            <div class="metric-label">Quality Score</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${status === 'completed' ? '🟢' : '🟡'} ${status}</div>
                            <div class="metric-label">Status</div>
                        </div>
                    </div>
            `;

            // Executive Summary
            if (synthesis.summary) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-file-alt"></i>
                            Executive Summary
                        </div>
                        <div class="summary-content markdown-content">
                            ${marked.parse(synthesis.summary)}
                        </div>
                    </div>
                `;
            }

            // Key Findings with expandable details
            if (synthesis.key_findings && synthesis.key_findings.length > 0) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-search"></i>
                            Key Findings
                        </div>
                `;
                
                synthesis.key_findings.slice(0, 8).forEach((finding, index) => {
                    const findingTitle = finding.finding || 'Research Finding';
                    const truncatedTitle = findingTitle.length > 100 ? findingTitle.substring(0, 100) + '...' : findingTitle;
                    
                    let findingContent = `
                        <div class="finding-detail">
                            <p><strong>Finding:</strong> ${marked.parse(finding.finding || 'N/A')}</p>
                            <p><strong>Evidence Level:</strong> ${finding.evidence_level || 'N/A'}</p>
                    `;
                    findingContent += '</div>';
                    
                    html += createExpandableSection(`Finding ${index + 1}: ${truncatedTitle}`, findingContent);
                });
                
                html += '</div>';
            }

            // Research Gaps & Opportunities
            if (synthesis.research_gaps && synthesis.research_gaps.length > 0) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-microscope"></i>
                            Research Gaps & Opportunities
                        </div>
                `;
                
                synthesis.research_gaps.slice(0, 5).forEach((gap, index) => {
                    html += `
                        <div class="gap-item">
                            <div class="gap-content">
                                <p><strong>Gap:</strong> ${marked.parse(gap.gap || 'N/A')}</p>
                                <p><strong>Significance:</strong> ${marked.parse(gap.significance || 'N/A')}</p>
                                <p><strong>Suggested Direction:</strong> ${marked.parse(gap.suggested_direction || 'N/A')}</p>
                            </div>
                            ${index < synthesis.research_gaps.length - 1 ? '<div class="divider"></div>' : ''}
                        </div>
                    `;
                });
                
                html += '</div>';
            }

            // Methodology Trends
            if (synthesis.methodology_trends && synthesis.methodology_trends.length > 0) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-cogs"></i>
                            Methodology Trends
                        </div>
                        <div class="trend-list">
                            ${synthesis.methodology_trends.map(trend => `
                                <div class="trend-item">${marked.parse(trend)}</div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            // Future Research Directions
            if (synthesis.future_directions && synthesis.future_directions.length > 0) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-rocket"></i>
                            Future Research Directions
                        </div>
                        <div class="direction-list">
                            ${synthesis.future_directions.map(direction => `
                                <div class="direction-item">${marked.parse(direction)}</div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            // Citation Network Analysis
            if (synthesis.citation_network) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-chart-bar"></i>
                            Citation Analysis
                        </div>
                `;
                
                const citation_data = synthesis.citation_network;
                
                // Citation Statistics
                if (citation_data.citation_stats) {
                    const stats = citation_data.citation_stats;
                    html += `
                        <div class="citation-stats">
                            <div class="metrics-grid">
                                <div class="metric-card">
                                    <div class="metric-value">${Math.round(stats.average_citations || 0)}</div>
                                    <div class="metric-label">Average Citations</div>
                                </div>
                                <div class="metric-card">
                                    <div class="metric-value">${stats.max_citations || 0}</div>
                                    <div class="metric-label">Max Citations</div>
                                </div>
                                <div class="metric-card">
                                    <div class="metric-value">${stats.total_citations || 0}</div>
                                    <div class="metric-label">Total Citations</div>
                                </div>
                            </div>
                        </div>
                    `;
                }
                
                // Highly Cited Papers
                if (citation_data.highly_cited_papers && citation_data.highly_cited_papers.length > 0) {
                    html += `
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
                }
                
                html += '</div>';
            }

            // Timeline Analysis
            if (synthesis.timeline_insights && synthesis.timeline_insights.length > 0) {
                html += `
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-calendar-alt"></i>
                            Temporal Trends
                        </div>
                        <div class="timeline-insights">
                            ${synthesis.timeline_insights.map(insight => `
                                <div class="timeline-item">
                                    <strong>${insight.trend || 'N/A'}:</strong> ${marked.parse(insight.description || 'N/A')}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            html += '</div>';
            
            // Add the toggle function for expandable sections
            if (!window.toggleSectionDefined) {
                window.toggleSection = function(sectionId) {
                    const content = document.getElementById(sectionId);
                    const icon = document.getElementById(sectionId + '-icon');
                    
                    if (content.classList.contains('expanded')) {
                        content.classList.remove('expanded');
                        icon.className = 'fas fa-chevron-right';
                    } else {
                        content.classList.add('expanded');
                        icon.className = 'fas fa-chevron-down';
                    }
                };
                window.toggleSectionDefined = true;
            }
            
            return html;
        }


        // Handle knowledge search
        async function handleKnowledgeSearch(message) {
            try {
                // Extract search terms from message
                const searchTerms = message.replace(/knowledge|database|search/gi, '').trim();
                
                if (!searchTerms) {
                    addMessage('assistant', '🔍 Please specify what you\'d like to search for in the knowledge base.');
                    return;
                }

                addMessage('assistant', `🔍 Searching knowledge base for: "${searchTerms}"`);

                const response = await fetch(`${API_BASE_URL}/search?query=${encodeURIComponent(searchTerms)}&k=10`);
                
                if (response.ok) {
                    const data = await response.json();
                    const resultsHtml = createKnowledgeSearchResults(data, searchTerms);
                    addMessage('assistant', resultsHtml, true);
                } else {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Search failed');
                }
                
            } catch (error) {
                addMessage('assistant', `❌ Knowledge search failed: ${error.message}`);
            }
        }

        // Create knowledge search results HTML
        function createKnowledgeSearchResults(data, searchTerms) {
            const results = data.results || [];
            
            if (results.length === 0) {
                return `
                    <div class="research-results">
                        <h3>🔍 Knowledge Search Results</h3>
                        <p>No results found for "${searchTerms}". Try different search terms or check if the knowledge base has been populated with relevant documents.</p>
                    </div>
                `;
            }

            return `
                <div class="research-results">
                    <h3>🔍 Knowledge Search Results</h3>
                    <p>Found ${results.length} relevant documents for: "${searchTerms}"</p>
                    
                    <div class="findings-section">
                        <div class="section-title">
                            <i class="fas fa-file-text"></i>
                            Search Results
                        </div>
                        ${results.map((result, index) => `
                            <div class="finding-item">
                                <div class="finding-title">Document ${index + 1}</div>
                                <div class="finding-evidence">${result.content || result.text || 'No preview available'}</div>
                                ${result.metadata ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem;">
                                    ${result.metadata.title ? `Title: ${result.metadata.title}<br>` : ''}
                                    ${result.metadata.authors ? `Authors: ${result.metadata.authors}<br>` : ''}
                                    Relevance: ${(result.score || 0).toFixed(3)}
                                </div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        // Handle statistics request
        async function handleStatisticsRequest() {
            try {
                addMessage('assistant', '📊 Loading knowledge base statistics...');

                const response = await fetch(`api/statistics`);
                
                if (response.ok) {
                    const data = await response.json();
                    const statsHtml = createStatisticsHTML(data);
                    addMessage('assistant', statsHtml, true);
                } else {
                    throw new Error('Failed to load statistics');
                }
                
            } catch (error) {
                addMessage('assistant', `❌ Failed to load statistics: ${error.message}`);
            }
        }

        // Create statistics HTML
        function createStatisticsHTML(data) {
            return `
                <div class="research-results">
                    <h3>📊 Knowledge Base Statistics</h3>
                    
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <div class="metric-value">${data.total_documents || 0}</div>
                            <div class="metric-label">Total Documents</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${data.unique_papers || 0}</div>
                            <div class="metric-label">Unique Papers</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${data.unique_authors || 0}</div>
                            <div class="metric-label">Authors</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${data.sample_size || 0}</div>
                            <div class="metric-label">Sample Size</div>
                        </div>
                    </div>

                    ${data.top_venues && data.top_venues.length > 0 ? `
                        <div class="findings-section">
                            <div class="section-title">
                                <i class="fas fa-trophy"></i>
                                Top Publication Venues
                            </div>
                            ${data.top_venues.slice(0, 5).map(venue => `
                                <div class="finding-item">
                                    <div class="finding-title">${venue.venue || 'Unknown Venue'}</div>
                                    <div class="finding-evidence">Papers: ${venue.count || 0}</div>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
        }
        // Show typing indicator
        function showTypingIndicator() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'typing-indicator';
            typingDiv.id = 'typing-indicator';
            typingDiv.innerHTML = `
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div>
                    <span>AI is thinking</span>
                    <div class="typing-dots" style="margin-top: 15px;">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                </div>
            `;
            chatMessages.appendChild(typingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        // Hide typing indicator
        function hideTypingIndicator() {
            const typingIndicator = document.getElementById('typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
        }

        // Set processing state
        function setProcessingState(processing) {
            isProcessing = processing;
            sendButton.disabled = processing;
            chatInput.disabled = processing;
        }

        // Perform knowledge search
        async function performKnowledgeSearch() {
            const query = document.getElementById('knowledge-search-input').value.trim();
            const resultsDiv = document.getElementById('knowledge-results');
            
            if (!query) {
                resultsDiv.innerHTML = '<p>Please enter a search query.</p>';
                return;
            }

            resultsDiv.innerHTML = '<p>Searching...</p>';

            try {
                const response = await fetch(`api/search?query=${encodeURIComponent(query)}&k=20`);
                
                if (response.ok) {
                    const data = await response.json();
                    displayKnowledgeResults(data.results || [], query);
                } else {
                    resultsDiv.innerHTML = '<p>Search failed. Please try again.</p>';
                }
            } catch (error) {
                console.error('Knowledge search error:', error);
                resultsDiv.innerHTML = '<p>Search error. Please try again.</p>';
            }
        }

        // Display knowledge search results
        function displayKnowledgeResults(results, query) {
            const resultsDiv = document.getElementById('knowledge-results');
            
            if (results.length === 0) {
                resultsDiv.innerHTML = `<p>No results found for "${query}". Try different search terms.</p>`;
                return;
            }

            const resultsHtml = `
                <h4>Search Results (${results.length} found)</h4>
                ${results.map((result, index) => `
                    <div class="result-item">
                        <div class="result-title">Result ${index + 1}</div>
                        <div class="result-content">${(result.content || result.text || 'No preview available').substring(0, 200)}...</div>
                        <div class="result-meta">
                            Relevance Score: ${(result.score || 0).toFixed(3)}
                            ${result.metadata?.title ? ` | Title: ${result.metadata.title}` : ''}
                        </div>
                    </div>
                `).join('')}
            `;
            
            resultsDiv.innerHTML = resultsHtml;
        }

        // Load statistics
        async function loadStatistics() {
            const statsGrid = document.getElementById('stats-grid');
            
            try {
                const response = await fetch(`api//statistics`);
                
                if (response.ok) {
                    const data = await response.json();
                    displayStatistics(data);
                } else {
                    statsGrid.innerHTML = `
                        <div class="stat-card">
                            <h3>Error Loading Statistics</h3>
                            <div class="value">---</div>
                            <div class="description">Failed to load data from API</div>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Statistics loading error:', error);
                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <h3>Connection Error</h3>
                        <div class="value">---</div>
                        <div class="description">Unable to connect to the API</div>
                    </div>
                `;
            }
        }

        // Display statistics
        function displayStatistics(data) {
            const statsGrid = document.getElementById('stats-grid');
            
            const statsHtml = `
                <div class="stat-card">
                    <h3>Total Documents</h3>
                    <div class="value">${data.total_documents || 0}</div>
                    <div class="description">Documents in knowledge base</div>
                </div>
                <div class="stat-card">
                    <h3>Unique Papers</h3>
                    <div class="value">${data.unique_papers || 0}</div>
                    <div class="description">Academic papers processed</div>
                </div>
                <div class="stat-card">
                    <h3>Authors</h3>
                    <div class="value">${data.unique_authors || 0}</div>
                    <div class="description">Unique authors identified</div>
                </div>
                <div class="stat-card">
                    <h3>Top Venue</h3>
                    <div class="value">${data.top_venue || 'None'}</div>
                    <div class="description">Top venue</div>
                </div>
            `;
            
            statsGrid.innerHTML = statsHtml;
        }

        // Load history page
        function loadHistoryPage() {
            const historyContent = document.getElementById('history-content');
            
            if (chatHistory.length === 0) {
                historyContent.innerHTML = '<p>No chats created yet. start your ressearch chat!</p>';
                return;
            }

            const historyHtml = `
                <div class="stat-card">
                    <h3>Chat History</h3>
                    <p>Total messages: ${chatHistory.length}</p>
                    <button class="search-button" onclick="exportChatHistory()">Export History</button>
                </div>
                <div class="search-results">
                    ${chatHistory.slice(-10).reverse().map((msg, index) => `
                        <div class="result-item">
                            <div class="result-title">${msg.sender === 'user' ? 'You' : 'AI Assistant'} - ${new Date(msg.timestamp).toLocaleString()}</div>
                            <div class="result-content">${msg.isHtml ? 'Research Results' : msg.content.substring(0, 150)}...</div>
                        </div>
                    `).join('')}
                </div>
            `;
            
            historyContent.innerHTML = historyHtml;
        }

        // Save chat history to localStorage
        function saveChatHistory() {
            try {
                const historyData = {
                    timestamp: new Date().toISOString(),
                    messages: chatHistory
                };
                window.chatHistoryData = historyData;
            } catch (error) {
                console.warn('Failed to save chat history:', error);
            }
        }

        // Load chat history from localStorage
        function loadChatHistory() {
            try {
                if (window.chatHistoryData) {
                    chatHistory = window.chatHistoryData.messages || [];
                    
                    // Restore messages to UI
                    chatHistory.forEach(msg => {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = `message ${msg.sender}`;
                        
                        const avatar = document.createElement('div');
                        avatar.className = 'message-avatar';
                        avatar.innerHTML = msg.sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
                        
                        const messageContent = document.createElement('div');
                        messageContent.className = 'message-content';
                        
                        const bubble = document.createElement('div');
                        bubble.className = 'message-bubble';
                        
                        if (msg.isHtml) {
                            bubble.innerHTML = msg.content;
                        } else {
                            bubble.textContent = msg.content;
                        }
                        
                        const timeDiv = document.createElement('div');
                        timeDiv.className = 'message-time';
                        timeDiv.textContent = new Date(msg.timestamp).toLocaleTimeString();
                        
                        messageContent.appendChild(bubble);
                        messageContent.appendChild(timeDiv);
                        messageDiv.appendChild(avatar);
                        messageDiv.appendChild(messageContent);
                        
                        // Only restore the welcome message if no history exists
                        if (chatHistory.length <= 1) {
                            chatMessages.appendChild(messageDiv);
                        }
                    });
                }
            } catch (error) {
                console.warn('Failed to load chat history:', error);
            }
        }

        // Clear chat history
        function clearChatHistory() {
            if (confirm('Are you sure you want to clear all chat history?')) {
                chatHistory = [];
                window.chatHistoryData = null;
                
                // Clear chat messages except welcome message
                const messages = chatMessages.querySelectorAll('.message');
                messages.forEach((msg, index) => {
                    if (index > 0) { // Keep the first welcome message
                        msg.remove();
                    }
                });
                
                alert('Chat history cleared successfully!');
            }
        }

        // Export chat history
        function exportChatHistory() {
            if (chatHistory.length === 0) {
                alert('No chat history to export.');
                return;
            }

            const exportData = {
                exported_at: new Date().toISOString(),
                total_messages: chatHistory.length,
                messages: chatHistory
            };

            const dataStr = JSON.stringify(exportData, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});
            
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `chat_history_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }

        // Utility function to format time
        function formatTime(timestamp) {
            return new Date(timestamp).toLocaleString();
        }

        function showAlert(type, message, duration = 3000) {
            // Remove existing alert if any
            const existingAlert = document.querySelector('.custom-alert');
            if (existingAlert) {
                existingAlert.remove();
            }
            
            const alert = document.createElement('div');
            alert.className = `custom-alert alert-${type}`;
            
            const icons = {
                success: 'fas fa-check-circle',
                error: 'fas fa-exclamation-circle',
                info: 'fas fa-info-circle'
            };
            
            alert.innerHTML = `
                <div class="alert-content">
                    <i class="${icons[type]}"></i>
                    <span class="alert-message">${message}</span>
                </div>
                <button class="alert-close" onclick="closeAlert(this)">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            document.body.appendChild(alert);
            
            // Trigger animation
            setTimeout(() => alert.classList.add('show'), 100);
            
            // Auto remove
            setTimeout(() => {
                closeAlert(alert.querySelector('.alert-close'));
            }, duration);
        }

        function closeAlert(button) {
            const alert = button.closest('.custom-alert');
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 300);
        }

        // Periodic API status check
        setInterval(checkApiStatus, 60000); // Check every minute