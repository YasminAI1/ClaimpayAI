document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chat-messages');
    const queryForm = document.getElementById('query-form');
    const queryInput = document.getElementById('query-input');
    
    // Handle form submission
    queryForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const query = queryInput.value.trim();
        if (!query) return;
        
        // Add user message to chat
        addMessage(query, 'user');
        
        // Clear input
        queryInput.value = '';
        
        // Show loading indicator
        const loadingMessage = addMessage('Thinking...', 'system loading');
        
        // Send query to server
        fetch('/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `query=${encodeURIComponent(query)}`
        })
        .then(response => response.json())
        .then(data => {
            // Remove loading message
            chatMessages.removeChild(loadingMessage);
            
            // Add response to chat
            addMessage(data.response, 'system');
            
            // Handle Excel download if present
            if (data.type === 'excel' && data.excel_url) {
                const downloadLink = document.createElement('a');
                downloadLink.href = data.excel_url;
                downloadLink.className = 'excel-download';
                downloadLink.innerText = '📊 Download Excel';
                downloadLink.target = '_blank';
                
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message system';
                messageDiv.appendChild(downloadLink);
                chatMessages.appendChild(messageDiv);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            chatMessages.removeChild(loadingMessage);
            addMessage('Sorry, an error occurred while processing your request.', 'system error');
        });
    });
    
    function addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        // Handle HTML content in responses
        if (text.includes('<a') || text.includes('<br')) {
            messageDiv.innerHTML = text;
        } else {
            // Convert line breaks to <br> tags
            messageDiv.innerText = text;
            messageDiv.innerHTML = messageDiv.innerHTML.replace(/\n/g, '<br>');
        }
        
        chatMessages.appendChild(messageDiv);
        
        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return messageDiv;
    }
});