from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import httpx
import uuid
from datetime import datetime, timedelta
import os
import logging
from werkzeug.utils import secure_filename
from functools import wraps, lru_cache
import json
import redis
from typing import Optional, Dict, Any
import time
import warnings
warnings.filterwarnings("ignore", message="Using the in-memory storage for tracking rate limits")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY'),
    'UPLOAD_FOLDER': os.getenv('UPLOAD_FOLDER', 'uploads'),
    'MAX_CONTENT_LENGTH': 32 * 1024 * 1024,  # 32MB
    'PERMANENT_SESSION_LIFETIME': timedelta(hours=24)
})

# Enable CORS with specific origins for production
CORS(app, origins=os.getenv('CORS_ORIGINS', '*').split(','))

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# API config
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

# Redis for caching (fallback to in-memory if Redis unavailable)
try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=0,
        decode_responses=True
    )
    redis_client.ping()
    USE_REDIS = True
    logger.info("Redis connected successfully")
except:
    redis_client = None
    USE_REDIS = False
    logger.warning("Redis not available, using in-memory storage")
    chat_sessions = {}
    research_cache = {}

# HTTP client with connection pooling
@lru_cache()
def get_http_client():
    return httpx.Client(
        base_url=API_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
    )

# ---------- Cache Management ---------- #
class CacheManager:
    @staticmethod
    def get(key: str) -> Optional[Any]:
        if USE_REDIS:
            try:
                value = redis_client.get(key)
                return json.loads(value) if value else None
            except:
                return None
        else:
            return research_cache.get(key)
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = 300):
        if USE_REDIS:
            try:
                redis_client.setex(key, ttl, json.dumps(value))
            except:
                pass
        else:
            research_cache[key] = value
    
    @staticmethod
    def delete(key: str):
        if USE_REDIS:
            try:
                redis_client.delete(key)
            except:
                pass
        else:
            research_cache.pop(key, None)

# ---------- Session Management ---------- #
class SessionManager:
    @staticmethod
    def create_session() -> str:
        session_id = str(uuid.uuid4())
        session_data = {
            "id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "messages": []
        }
        
        if USE_REDIS:
            try:
                redis_client.setex(
                    f"session:{session_id}", 
                    86400,  # 24 hours
                    json.dumps(session_data)
                )
            except:
                chat_sessions[session_id] = session_data
        else:
            chat_sessions[session_id] = session_data
        
        return session_id
    
    @staticmethod
    def get_session(session_id: str) -> Optional[Dict]:
        if USE_REDIS:
            try:
                data = redis_client.get(f"session:{session_id}")
                return json.loads(data) if data else None
            except:
                return chat_sessions.get(session_id)
        else:
            return chat_sessions.get(session_id)
    
    @staticmethod
    def update_session(session_id: str, session_data: Dict):
        if USE_REDIS:
            try:
                redis_client.setex(
                    f"session:{session_id}", 
                    86400,
                    json.dumps(session_data)
                )
            except:
                chat_sessions[session_id] = session_data
        else:
            chat_sessions[session_id] = session_data

# ---------- Decorators ---------- #
def validate_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json() if request.is_json else {}
        session_id = data.get('session_id') or request.args.get('session_id')
        
        if not session_id:
            return jsonify({"error": "Session ID required"}), 400
        
        session_data = SessionManager.get_session(session_id)
        if not session_data:
            return jsonify({"error": "Invalid session"}), 404
        
        return f(session_id, session_data, *args, **kwargs)
    return decorated_function

def cache_response(ttl=300):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"cache:{f.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            cached_result = CacheManager.get(cache_key)
            if cached_result:
                return jsonify(cached_result)
            
            # Execute function and cache result
            result = f(*args, **kwargs)
            if hasattr(result, 'get_json'):
                CacheManager.set(cache_key, result.get_json(), ttl)
            
            return result
        return decorated_function
    return decorator

# ---------- Helpers ---------- #
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_api_request(endpoint: str, method: str = 'GET', data: Dict = None, params: Dict = None) -> Optional[httpx.Response]:
    """Enhanced API request with retries and better error handling"""
    client = get_http_client()
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if method.upper() == 'GET':
                response = client.get(endpoint, params=params)
            elif method.upper() == 'POST':
                response = client.post(endpoint, json=data)
            else:
                response = client.request(method, endpoint, json=data, params=params)
            
            response.raise_for_status()
            return response
            
        except httpx.TimeoutException:
            logger.warning(f"Timeout on attempt {attempt + 1} for {endpoint}")
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {endpoint}")
            return e.response
            
        except Exception as e:
            logger.error(f"Request failed on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)
    
    return None

# ---------- Intent Handlers ---------- #
class IntentProcessor:
    @staticmethod
    def process_message(message: str) -> Dict[str, Any]:
        """Enhanced intent processing with better classification"""
        message_lower = message.lower().strip()
        
        # Research intent patterns
        research_patterns = [
            'search', 'find', 'research', 'papers', 'analyze', 'study', 
            'investigate', 'explore', 'discover', 'literature', 'academic',
            'what are', 'how does', 'compare', 'review'
        ]
        
        if any(pattern in message_lower for pattern in research_patterns):
            return IntentProcessor.handle_research_intent(message)
        else:
            return IntentProcessor.handle_general_intent(message)
    
    @staticmethod
    def handle_research_intent(message: str) -> Dict[str, Any]:
        """Handle research discovery requests"""
        try:
            research_data = {
                "query": message,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            response = make_api_request('/research', method='POST', data=research_data)
            
            if response and response.status_code == 200:
                api_data = response.json()
                return {
                    "request_id": api_data.get('request_id'),
                    "type": "research",
                    "content": f"🔍 Research started! Request ID: {api_data.get('request_id')}\n\nI'm discovering and analyzing papers related to: *{message}*\n\nThis may take a few minutes. You can check the progress using the request ID."
                }
            else:
                error_msg = "Failed to start research task"
                if response:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('detail', error_msg)
                    except:
                        pass
                
                return {
                    "type": "error",
                    "content": f"{error_msg}. Please try again or rephrase your query."
                }
                
        except Exception as e:
            logger.error(f"Research intent error: {e}")
            return {
                "type": "error",
                "content": "Sorry, I encountered an error while starting your research. Please try again."
            }
    
    @staticmethod
    def handle_general_intent(message: str) -> Dict[str, Any]:
        """Enhanced general conversation handling"""
        message_lower = message.lower()
        
        responses = {
            'greeting': "Hello! 👋 I'm your Academic Research Assistant. How I can help you?",
            
            'thanks': "You're very welcome! 😊 Feel free to ask about any research topics.",
            
            'capabilities': "I specialize in academic research assistance using AI agents for paper discovery, content extraction, and synthesis. I can search multiple databases, analyze trends, and provide comprehensive research insights.",
            
            'default': [
                "I'm here to help with your research! Try asking me to find papers on a specific topic.",
                "What research area interests you? I can discover relevant papers and analyze trends.",
                "Feel free to ask about specific research topics or upload documents to search.",
                "I can help you explore academic literature. What would you like to research?"
            ]
        }
        
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'greetings']):
            response_type = 'greeting'
        elif any(word in message_lower for word in ['thank', 'thanks', 'appreciate']):
            response_type = 'thanks'
        elif any(word in message_lower for word in ['what can you', 'capabilities', 'what do you do']):
            response_type = 'capabilities'
        else:
            response_type = 'default'
        
        if response_type == 'default':
            content = responses[response_type][hash(message) % len(responses[response_type])]
        else:
            content = responses[response_type]
        
        return {
            'type': 'text',
            'content': content
        }

# ---------- Routes ---------- #
@app.route('/')
def index():
    """Main application page"""
    return render_template('index.html')

@app.route('/health')
@limiter.exempt
def health_check():
    """Enhanced health check"""
    try:
        # Check API connectivity
        api_response = make_api_request('/')
        api_healthy = api_response and api_response.status_code == 200
        
        # Check Redis connectivity
        redis_healthy = True
        if USE_REDIS:
            try:
                redis_client.ping()
            except:
                redis_healthy = False
        
        return jsonify({
            "status": "healthy" if api_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "api": "healthy" if api_healthy else "unhealthy",
                "redis": "healthy" if redis_healthy else "unhealthy",
                "storage": "healthy"
            }
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 503

@app.route('/api/session/start', methods=['POST'])
@limiter.limit("10 per minute")
def start_chat_session():
    """Start a new chat session"""
    session_id = SessionManager.create_session()
    return jsonify({"session_id": session_id})

@app.route('/api/chat', methods=['POST'])
@limiter.limit("30 per minute")
@validate_session
def chat(session_id: str, session_data: Dict):
    """Enhanced chat endpoint with better error handling"""
    data = request.get_json()
    message = data.get('message', '').strip()

    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400

    try:
        # Store user message
        user_msg = {
            'id': str(uuid.uuid4()),
            'sender': 'user',
            'content': message,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Process message with enhanced intent handling
        ai_response = IntentProcessor.process_message(message)
        
        ai_msg = {
            'id': str(uuid.uuid4()),
            'sender': 'assistant',
            'request_id': ai_response.get('request_id'),
            'content': ai_response['content'],
            'type': ai_response.get('type', 'text'),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Update session
        session_data['messages'].extend([user_msg, ai_msg])
        SessionManager.update_session(session_id, session_data)

        return jsonify(ai_msg)
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({
            "error": "Failed to process message",
            "content": "I apologize, but I encountered an error processing your message. Please try again."
        }), 500

@app.route('/api/chat/history/<session_id>')
@limiter.limit("20 per minute")
def get_chat_history(session_id: str):
    """Get chat history with pagination"""
    session_data = SessionManager.get_session(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    messages = session_data["messages"]
    total = len(messages)
    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        "session_id": session_id,
        "messages": messages[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        },
        "created_at": session_data["created_at"]
    })

@app.route('/api/upload', methods=['POST'])
@limiter.limit("5 per minute")
def upload_files():
    """Enhanced file upload with better validation"""
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
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    for file in files:
        if file and file.filename != '':
            if allowed_file(file.filename):
                try:
                    filename = secure_filename(file.filename)
                    # Add timestamp to prevent conflicts
                    name, ext = os.path.splitext(filename)
                    filename = f"{name}_{int(time.time())}{ext}"
                    
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    
                    file_info = {
                        "original_name": file.filename,
                        "stored_name": filename,
                        "file_size": os.path.getsize(file_path),
                        "upload_time": datetime.utcnow().isoformat()
                    }
                    
                    results["uploaded_files"].append(file_info)
                    results["success_count"] += 1
                    
                except Exception as e:
                    logger.error(f"Upload error for {file.filename}: {e}")
                    results["errors"].append(f"Error saving {file.filename}: {str(e)}")
                    results["error_count"] += 1
            else:
                results["errors"].append(f"File type not allowed: {file.filename}")
                results["error_count"] += 1
    
    if results["success_count"] > 0:
        # Clear cache for statistics
        CacheManager.delete("statistics")
        
        return jsonify({
            "message": f"Successfully uploaded {results['success_count']} file(s)",
            "uploaded_files": results["uploaded_files"],
            "success_count": results["success_count"],
            "errors": results["errors"] if results["errors"] else []
        }), 200
    else:
        return jsonify({
            "error": "All uploads failed",
            "errors": results["errors"],
            "error_count": results["error_count"]
        }), 400

@app.route('/api/process_uploaded_files', methods=['POST'])
@limiter.limit("2 per minute")
def process_uploaded_files():
    """Process uploaded files with enhanced error handling"""
    try:
        response = make_api_request(
            "/update_knowledgebase", 
            "POST", 
            {"upload_path": app.config['UPLOAD_FOLDER']}
        )
        
        if response and response.status_code == 200:
            response_data = response.json()
            # Clear caches
            CacheManager.delete("statistics")
            
            return jsonify({
                "message": f"Success! Added {response_data['processed_count']} file(s) to knowledge base",
                "processed_count": response_data["processed_count"],
                "details": response_data.get("details", [])
            }), 200
            
        elif response and response.status_code == 400:
            response_data = response.json()
            return jsonify({
                "error": "Processing failed",
                "message": response_data.get("detail", "Failed to process files"),
                "error_count": response_data.get("error_count", 0)
            }), 400
        else:
            return jsonify({
                "error": "Internal processing error",
                "message": "Failed to process uploaded files"
            }), 500
            
    except Exception as e:
        logger.error(f"File processing error: {e}")
        return jsonify({
            "error": "Processing failed",
            "message": str(e)
        }), 500

@app.route('/api/statistics')
@cache_response(ttl=300)  # Cache for 5 minutes
def get_statistics():
    """Get knowledge base statistics with caching"""
    try:
        response = make_api_request('/statistics')
        
        if response and response.status_code == 200:
            return jsonify(response.json())
        else:
            # Return default statistics
            return jsonify({
                "total_documents": 0,
                "unique_papers": 0,
                "unique_authors": 0,
                "sample_size": 0,
                "top_venues": [],
                "extraction_methods": {},
                "last_updated": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        return jsonify({
            "error": "Failed to fetch statistics",
            "total_documents": 0,
            "unique_papers": 0,
            "unique_authors": 0
        }), 500

@app.route('/api/research/<request_id>/status')
@limiter.limit("60 per minute")
def get_research_status(request_id: str):
    """Get research task status with caching"""
    try:
        
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
            "progress": 0,
            "error": str(e)
        }), 500

@app.route('/api/research/<request_id>/results')
@cache_response(ttl=3600)  # Cache results for 1 hour
def get_research_results(request_id: str):
    """Get research results with enhanced caching"""
    try:
        response = make_api_request(f'/research/{request_id}/results')
        
        if response and response.status_code == 200:
            return jsonify(response.json())
        elif response and response.status_code == 404:
            return jsonify(response.json()), 404
        else:
            error_msg = "Failed to get results"
            if response:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text[:200]
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Results retrieval error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/search')
@limiter.limit("30 per minute")
def search_knowledge_base():
    """Enhanced knowledge base search"""
    query = request.args.get('query', '').strip()
    k = request.args.get('k', 10, type=int)
    
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400
    
    # Validate k parameter
    k = max(1, min(k, 50))  # Limit between 1 and 50
    
    try:
        response = make_api_request('/search', params={'query': query, 'k': k})
        
        if response and response.status_code == 200:
            results = response.json()
            
            # Add search metadata
            results['search_metadata'] = {
                'query': query,
                'requested_count': k,
                'actual_count': len(results.get('results', [])),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return jsonify(results)
        else:
            error_msg = "Search failed"
            if response:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text[:200]
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/clusters')
@cache_response(ttl=600)  # Cache for 10 minutes
def get_research_clusters():
    """Get research clusters with caching"""
    query = request.args.get('query', '')
    k = request.args.get('k', 30, type=int)
    
    k = max(5, min(k, 100))  # Limit between 5 and 100
    
    try:
        response = make_api_request('/clusters', params={'query': query, 'k': k})
        
        if response and response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"clusters": [], "message": "No clusters available"}), 200
            
    except Exception as e:
        logger.error(f"Clusters error: {e}")
        return jsonify({"clusters": [], "error": str(e)}), 200

# ---------- Error Handlers ---------- #
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "message": "The requested resource was not found"
    }), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later."
    }), 429

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500

# ---------- Cleanup ---------- #
@app.teardown_appcontext
def cleanup(error):
    """Cleanup resources"""
    pass

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Log startup info
    logger.info("Starting Academic Research Assistant")
    logger.info(f"Redis enabled: {USE_REDIS}")
    
    # Run application
    app.run(
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )