from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import uuid
from datetime import datetime
import os
import logging
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Enable CORS
CORS(app, origins=["*"])

# API config
API_BASE_URL = "http://localhost:8000"
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}

# In-memory storage
chat_sessions = {}
research_cache = {}

# ---------- Helpers ---------- #
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_api_request(endpoint, method='GET', data=None, params=None):
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == 'GET':
            return requests.get(url, params=params, timeout=30)
        elif method == 'POST':
            return requests.post(url, json=data, timeout=30)
        else:
            return requests.request(method, url, json=data, params=params, timeout=30)
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None

# ---------- Intent Handlers ---------- #
def process_chat_message(message):
    message_lower = message.lower()
    research_keywords = ['search', 'find', 'research', 'papers', 'analyze', 'study', 'investigate']

    if any(keyword in message_lower for keyword in research_keywords):
        return handle_research_intent(message)
    else:
        return handle_general_intent(message)

def handle_research_intent(message):
        query = message
        
        # Prepare research parameters
        research_data = {
            "query": query
        }
        
        # Make request to research API
        response = make_api_request('/research', method='POST', data=research_data)
        
        if response and response.status_code == 200:
            api_data = response.json()
            request_id = api_data.get('request_id')
            
            return {
                "request_id": request_id,
                "type": "research",
                "content": f"Research started for request id: {request_id}"
            }
        else:            
            return {"error": response.json(), 'content': "Sorry i couldn't start the research task"}, 500

def handle_general_intent(message):
    """Handle general conversation messages"""
    responses = [
        "I'm here to help you with academic research! You can ask me to search for papers, analyze research trends, or explore our knowledge base.",
        "Feel free to ask me about specific research topics. I can help you discover papers, synthesize findings, and identify research gaps.",
        "I specialize in academic research assistance. Try asking me to 'find papers on [topic]' or 'analyze research in [field]'.",
        "What research topic would you like to explore? I can search academic databases and provide comprehensive analysis."
    ]
    
    # Simple response selection based on message content
    if 'hello' in message.lower() or 'hi' in message.lower():
        response = "Hello! I'm your Academic Research Assistant. How can I help you with your research today?"
    elif 'help' in message.lower():
        response = """I can help you with:

🔍 **Research Discovery**: Find and analyze academic papers
📚 **Knowledge Search**: Search through processed documents  
📊 **Analytics**: View statistics and trends
💬 **General Questions**: Answer research-related queries

Try asking: "Find papers on machine learning" or "Search knowledge base for COVID-19 research"
"""
    elif 'thank' in message.lower():
        response = "You're welcome! Feel free to ask if you need help with any research topics."
    else:
        response = responses[hash(message) % len(responses)]
    
    return {
        'content': response,
        'type': 'text'
    }

# ---------- Routes ---------- #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "api_status": "checking..."
    })

@app.route('/api/status')
def api_status():
    """Check the status of the research API"""
    try:
        response = make_api_request('/')
        if response and response.status_code == 200:
            return jsonify({
                "status": "online",
                "api_responsive": True,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            return jsonify({
                "status": "error",
                "api_responsive": False,
                "timestamp": datetime.utcnow().isoformat()
            }), 502
    except Exception as e:
        return jsonify({
            "status": "offline",
            "api_responsive": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 503

@app.route('/api/session/start', methods=['POST'])
def start_chat_session():
    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {
        "id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "messages": []
    }
    return jsonify({"session_id": session_id})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    session_id = data.get('session_id')
    message = data.get('message', '').strip()

    if not session_id or session_id not in chat_sessions:
        return jsonify({"error": "Invalid session"}), 400
    if not message:
        return jsonify({"error": "Empty message"}), 400

    # Store user message
    user_msg = {
        'id': str(uuid.uuid4()),
        'sender': 'user',
        'content': message,
        'timestamp': datetime.utcnow().isoformat()
    }
    # Process and store AI response
    ai_response = process_chat_message(message) 
    ai_msg = {
        'id': str(uuid.uuid4()),
        'sender': 'assistant',
        'request_id': ai_response.get('request_id', None),
        'content': ai_response['content'],
        'type': ai_response.get('type', 'text'),
        'timestamp': datetime.utcnow().isoformat(),
        'error': ai_response.get("error", None)
    }

    if 'error' in ai_response:
        return jsonify({"error": "Error processing message"}), 404
    
    # Append messages to session
    chat_sessions[session_id]['messages'].append(user_msg)
    chat_sessions[session_id]['messages'].append(ai_msg)

    return ai_msg

@app.route('/api/chat/history/<session_id>')
def get_chat_history(session_id):
    """Get chat history for a session"""
    if session_id not in chat_sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = chat_sessions[session_id]
    return jsonify({
        "session_id": session_id,
        "messages": session["messages"],
        "created_at": session["created_at"]
    })
    
@app.route('/api/upload', methods=['POST'])
def upload_files():
    # Check if files are present in request
    if 'files' not in request.files:
        return jsonify({"error": "No files provided"}), 400
    
    files = request.files.getlist('files')
    
    if not files or all(file.filename == '' for file in files):
        return jsonify({"error": "No files selected"}), 400
    
    results = {
        "success_count": 0,
        "error_count": 0,
        "uploaded_files": [],
        "errors": []
    }
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    for file in files:
        if file and file.filename != '':
            if allowed_file(file.filename):
                try:
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    
                    # Add to successful uploads
                    results["uploaded_files"].append({
                        "filename": filename,
                        "file_size": os.path.getsize(file_path)
                    })
                    results["success_count"] += 1
                    
                except Exception as e:
                    results["errors"].append(f"Error saving {file.filename}: {str(e)}")
                    results["error_count"] += 1
            else:
                results["errors"].append(f"File type not allowed: {file.filename}")
                results["error_count"] += 1
    
    # Return appropriate response
    if results["success_count"] > 0 and results["error_count"] == 0:
        return jsonify({
            "message": f"Successfully uploaded {results['success_count']} file(s)",
            "uploaded_files": results["uploaded_files"],
            "success_count": results["success_count"]
        }), 200
    
    else:
        return jsonify({
            "error": "upload failed",
            "errors": results["errors"],
            "error_count": results["error_count"]
        }), 400
    
@app.route('/api/process_uploaded_files', methods=['GET'])
def process_uploaded_files():
    try:
    
        # Check status with the research API
        response = make_api_request("/update_knowledgebase","POST", {"upload_path": app.config['UPLOAD_FOLDER']})
        
        if response and response.status_code == 200:
            response_data = response.json() 
            return jsonify({
            "message": f"{response_data['status']}! added  {response_data['processed_count']} file(s) to knowledge base",
            "success_count": response_data["processed_count"]
        }), 200
        elif response and response.status_code == 400:
            return jsonify({
            "message": f"Failed to process uploaded files",
            "failure_count": response_data["error_count"]
        }), 400
        else:
            return jsonify({
                "status": "Internal Error",
                "message": "Failed to process files"
            }), 500
        
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/api/statistics')
def get_statistics():
    """Get knowledge base statistics"""
    try:
        # Check cache first
        if "statistics" in research_cache:
            cached_stats = research_cache["statistics"]
            # Return cached stats if less than 5 minutes old
            cache_time = datetime.fromisoformat(cached_stats.get("cached_at", "2020-01-01"))
            if (datetime.utcnow() - cache_time).seconds < 300:
                return jsonify(cached_stats["data"])
        
        # Get fresh statistics
        response = make_api_request('/statistics')
        
        if response and response.status_code == 200:
            stats_data = response.json()
            
            # Cache the statistics
            research_cache["statistics"] = {
                "data": stats_data,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            return jsonify(stats_data)
        else:
            # Return default statistics if API fails
            return jsonify({
                "total_documents": 0,
                "unique_papers": 0,
                "unique_authors": 0,
                "sample_size": 0,
                "top_venues": [],
                "extraction_methods": {}
            })
            
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        return jsonify({
            "total_documents": 0,
            "unique_papers": 0,
            "unique_authors": 0,
            "sample_size": 0,
            "top_venues": [],
            "extraction_methods": {}
        }), 200
    
@app.route('/api/research/<request_id>/status')
def get_research_status(request_id):
    """Get the status of a research task"""
    
    try:
        
        # Check status with the research API
        response = make_api_request(f'/research/{request_id}/status')
        
        if response and response.status_code == 200:
            status_data = response.json()
            
            return jsonify(status_data)
        elif response and response.status_code == 404:
            return jsonify(response.json()), 404
        else:
            return jsonify({
                "status": "error",
                "progress": 0,
                "error": "Failed to check status"
            }), 500
            
    except Exception as e:
        logger.error(f"Status check error: {e}")
        return jsonify({
            "status": "error",
            "progress": "unknown", 
            "error": str(e)
        }), 500

@app.route('/api/research/<request_id>/results')
def get_research_results(request_id):
    """Get the results of a research task"""
    
    try:        
        # Check cache first
        cache_key = f"results_{request_id}"
        if cache_key in research_cache:
            return jsonify(research_cache[cache_key])
        
        # Get results from research API
        response = make_api_request(f'/research/{request_id}/results')
        
        if response and response.status_code == 200:
            results_data = response.json()
            
            # Cache the results
            research_cache[cache_key] = results_data
            
            return jsonify(results_data)
        elif response and response.status_code == 404:
            return jsonify(response.json()), 404
        else:
            error_msg = "Failed to get results"
            if response:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Results retrieval error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/search')
def search_knowledge_base():
    """Search the knowledge base"""
    query = request.args.get('query', '')
    k = request.args.get('k', 10, type=int)
    
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400
    
    try:
        # Search knowledge base via API
        response = make_api_request('/search', params={'query': query, 'k': k})
        
        if response and response.status_code == 200:
            return jsonify(response.json())
        else:
            error_msg = "Search failed"
            if response:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/clusters')
def get_research_clusters():
    """Get research clusters"""
    query = request.args.get('query', '')
    k = request.args.get('k', 30, type=int)
    
    try:
        # Get clusters via API
        response = make_api_request('/clusters', params={'query': query, 'k': k})
        
        if response and response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"clusters": []}), 200
            
    except Exception as e:
        logger.error(f"Clusters error: {e}")
        return jsonify({"clusters": []}), 200

# ---------- Error Handlers ---------- #
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    logger.info("Starting Academic Research Assistant API")
    app.run(host='0.0.0.0', port=5000, debug=True)
