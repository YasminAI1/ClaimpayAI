# Execute this as a Python script to create the templates directory and index.html
import os

# Create templates directory
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
os.makedirs(templates_dir, exist_ok=True)

# Write your existing HTML to the index.html file
with open(os.path.join(templates_dir, 'index.html'), 'w') as f:
    f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Claimpay AI Chatbot</title>
    <style>
        /* Previous styles remain the same */
    body { 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background-image: url('./static/background.webp');  /* Relative path */
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            min-height: 100vh;
            background-color: #f5f5f5; /* Fallback color */
        }      
            .chat-container { 
            max-width: 800px; 
            margin: auto; 
            background-color: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            padding: 20px;
            backdrop-filter: blur(5px);
        }         

        .chat-box { 
            border: 1px solid #ccc;
            padding: 20px;
            height: 400px;
            overflow-y: auto;
            margin-bottom: 20px;
            border-radius: 5px;
            background-color: rgba(255, 255, 255, 0.9);
        }

        .input-box {
            width: calc(100% - 100px);
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
        }

        .message { 
            margin: 10px 0;
            padding: 10px;
            border-radius: 5px;
        }

        .user-message { 
            background-color: #e3f2fd;
            color: #1976d2;
            margin-left: 20px;
        }

        .bot-message { 
            background-color: #f1f8e9;
            color: #388e3c;
            margin-right: 20px;
        }

        button {
            padding: 10px 20px;
            background-color: #2196f3;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }

        button:hover {
            background-color: #1976d2;
        }

        .claim-link {
            color: #2196f3;
            text-decoration: none;
            margin-top: 5px;
            display: inline-block;
        }

        .claim-link:hover {
            text-decoration: underline;
        }

        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 10px;
        }

        th, td { 
            border: 1px solid #ddd; 
            padding: 8px; 
            text-align: left; 
        }

        /* Add new Excel download button style */

        .message pre {
            white-space: pre-wrap;
            font-family: monospace;
            margin: 10px 0;
            padding: 10px;
            background-color: rgba(0,0,0,0.05);
            border-radius: 4px;
        }

        .excel-download {
            display: inline-block;
            padding: 8px 15px;
            background-color: #1d6f42;
            color: white !important;
            text-decoration: none;
            border-radius: 5px;
            margin-top: 10px;
            font-size: 14px;
        }

        .excel-download:hover {
            background-color: #155a35;
        }

            /* Mobile responsiveness */
            @media (max-width: 768px) {
                .chat-container {
                    margin: 10px;
                    padding: 10px;
                }

                .input-box {
                    width: calc(100% - 80px);
                }

        }
    </style>
</head>
<body>
    <div class="chat-container">
        <h1>ClaimPay AI Chat</h1>
        <div class="chat-box" id="chatBox">
            <div class="message bot-message">
                Hello! I can help you with claims information. Try asking questions like:
                <br>- Show me claims from today
                <br>- What is the status of claim number [number]?
                <br>- Show me claims with high bill amounts
                <br>- Export claims to Excel
            </div>
        </div>
        <form id="queryForm" onsubmit="sendQuery(); return false;">
            <input type="text" id="userInput" class="input-box" placeholder="Ask your question...">
            <button type="submit">Send</button>
        </form>
    </div>

    <script>
        function sendQuery() {
            const input = document.getElementById('userInput');
            const query = input.value;
            
            if (!query.trim()) return;
    
            const chatBox = document.getElementById('chatBox');
            chatBox.innerHTML += `<div class="message user-message">You: ${query}</div>`;
            
            fetch('/query', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'query=' + encodeURIComponent(query)
            })
            .then(response => response.json())
            .then(data => {
                let responseHtml = `<div class="message bot-message">`;
                
                // Add the main response
                responseHtml += data.response;
                
                // Close the message div
                responseHtml += `</div>`;
                
                chatBox.innerHTML += responseHtml;
                chatBox.scrollTop = chatBox.scrollHeight;
                input.value = '';
            })
            .catch(error => {
                chatBox.innerHTML += `
                    <div class="message bot-message" style="color: red;">
                        Error: ${error.message}
                    </div>
                `;
                chatBox.scrollTop = chatBox.scrollHeight;
            });
        }
    </script>
</body>
</html>""")