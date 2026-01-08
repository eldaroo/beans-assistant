/**
 * Chat Widget Component
 * 
 * Provides a floating chat interface that communicates with the tenant-specific chat API.
 * Automatically detects the current tenant from the URL and maintains conversation history.
 */

class ChatWidget {
    constructor(tenantPhone) {
        this.tenantPhone = tenantPhone;
        this.messages = [];
        this.isOpen = false;
        this.isTyping = false;
        
        this.init();
    }

    init() {
        // Create widget HTML
        this.createWidget();
        
        // Attach event listeners
        this.attachEventListeners();
        
        // Add welcome message
        this.addWelcomeMessage();
    }

    createWidget() {
        const widgetHTML = `
            <div id="chat-widget">
                <!-- Toggle Button -->
                <button id="chat-toggle-btn" aria-label="Toggle chat">
                    💬
                </button>

                <!-- Chat Window -->
                <div id="chat-window">
                    <!-- Header -->
                    <div id="chat-header">
                        <h3>🤖 Asistente de IA</h3>
                        <button id="chat-close-btn" aria-label="Close chat">×</button>
                    </div>

                    <!-- Messages -->
                    <div id="chat-messages">
                        <!-- Messages will be inserted here -->
                    </div>

                    <!-- Typing Indicator -->
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>

                    <!-- Input -->
                    <div id="chat-input-container">
                        <input 
                            type="text" 
                            id="chat-input" 
                            placeholder="Escribe tu mensaje..."
                            autocomplete="off"
                        />
                        <button id="chat-send-btn" aria-label="Send message">
                            ➤
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', widgetHTML);
    }

    attachEventListeners() {
        const toggleBtn = document.getElementById('chat-toggle-btn');
        const closeBtn = document.getElementById('chat-close-btn');
        const sendBtn = document.getElementById('chat-send-btn');
        const input = document.getElementById('chat-input');

        // Toggle chat window
        toggleBtn.addEventListener('click', () => this.toggleChat());
        closeBtn.addEventListener('click', () => this.closeChat());

        // Send message
        sendBtn.addEventListener('click', () => this.sendMessage());
        
        // Send on Enter key
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    toggleChat() {
        const chatWindow = document.getElementById('chat-window');
        this.isOpen = !this.isOpen;
        
        if (this.isOpen) {
            chatWindow.classList.add('open');
            document.getElementById('chat-input').focus();
        } else {
            chatWindow.classList.remove('open');
        }
    }

    closeChat() {
        const chatWindow = document.getElementById('chat-window');
        chatWindow.classList.remove('open');
        this.isOpen = false;
    }

    addWelcomeMessage() {
        const messagesContainer = document.getElementById('chat-messages');
        const welcomeHTML = `
            <div class="welcome-message">
                <div class="welcome-message-icon">👋</div>
                <p>¡Hola! Soy tu asistente de IA.<br>Pregúntame sobre productos, ventas, stock o registra operaciones.</p>
            </div>
        `;
        messagesContainer.innerHTML = welcomeHTML;
    }

    addMessage(text, isUser = false) {
        const messagesContainer = document.getElementById('chat-messages');
        
        // Remove welcome message if it exists
        const welcomeMsg = messagesContainer.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }

        const messageHTML = `
            <div class="chat-message ${isUser ? 'user' : 'agent'}">
                <div class="message-bubble">${this.escapeHtml(text)}</div>
            </div>
        `;

        messagesContainer.insertAdjacentHTML('beforeend', messageHTML);
        this.scrollToBottom();

        // Store message
        this.messages.push({ text, isUser, timestamp: new Date() });
    }

    showTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator');
        indicator.classList.add('active');
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator');
        indicator.classList.remove('active');
    }

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();

        if (!message) return;

        // Clear input
        input.value = '';

        // Add user message to chat
        this.addMessage(message, true);

        // Show typing indicator
        this.showTypingIndicator();

        try {
            // Build URL with detailed logging
            const encodedPhone = encodeURIComponent(this.tenantPhone);
            const url = `/api/tenants/${encodedPhone}/chat`;
            
            console.log('[Chat Widget] Sending message...');
            console.log('[Chat Widget] Tenant phone:', this.tenantPhone);
            console.log('[Chat Widget] Encoded phone:', encodedPhone);
            console.log('[Chat Widget] Full URL:', url);
            console.log('[Chat Widget] Message:', message);
            
            // Send message to API (encode phone number for URL)
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            });

            console.log('[Chat Widget] Response status:', response.status);
            console.log('[Chat Widget] Response OK:', response.ok);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('[Chat Widget] Error response:', errorText);
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('[Chat Widget] Response data:', data);

            // Hide typing indicator
            this.hideTypingIndicator();

            // Add agent response
            this.addMessage(data.response, false);

        } catch (error) {
            console.error('[Chat Widget] Error sending message:', error);
            console.error('[Chat Widget] Error stack:', error.stack);
            
            // Hide typing indicator
            this.hideTypingIndicator();

            // Show error message
            this.addErrorMessage('Lo siento, hubo un error al procesar tu mensaje. Por favor intenta de nuevo.');
        }
    }

    addErrorMessage(text) {
        const messagesContainer = document.getElementById('chat-messages');
        const errorHTML = `
            <div class="error-message">
                ⚠️ ${this.escapeHtml(text)}
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', errorHTML);
        this.scrollToBottom();
    }

    scrollToBottom() {
        const messagesContainer = document.getElementById('chat-messages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Extract tenant phone from URL
    const pathParts = window.location.pathname.split('/');
    const tenantIndex = pathParts.indexOf('tenants');
    
    if (tenantIndex !== -1 && pathParts[tenantIndex + 1]) {
        const tenantPhone = pathParts[tenantIndex + 1];
        
        // Initialize chat widget
        window.chatWidget = new ChatWidget(tenantPhone);
        
        console.log(`[Chat Widget] Initialized for tenant: ${tenantPhone}`);
        console.log(`[Chat Widget] API endpoint will be: /api/tenants/${encodeURIComponent(tenantPhone)}/chat`);
    } else {
        console.log('[Chat Widget] Not on a tenant page, widget not initialized');
        console.log(`[Chat Widget] Path parts:`, pathParts);
    }
});
