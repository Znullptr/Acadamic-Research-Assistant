# Academic Research Assistant - Deployment Guide

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone or create project directory
mkdir academic_research_assistant
cd academic_research_assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install system dependencies for OCR
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr poppler-utils

# macOS:
brew install tesseract poppler

# Windows: Download and install Tesseract from GitHub
```

### 2. Configuration

Create `.env` file in the project root:

```env
# Required API Keys
OPENAI_API_KEY=sk-your-openai-api-key-here
GOOGLE_API_KEY=your-google-api-key-here
GOOGLE_CSE_ID=your-custom-search-engine-id

# Optional API Keys
SEMANTIC_SCHOLAR_API_KEY=your-semantic-scholar-key

# Database Configuration
CHROMA_DB_PATH=./chroma_db

# Processing Settings
MAX_PAPERS_PER_SEARCH=50
OCR_LANGUAGE=eng
LOG_LEVEL=INFO

# Performance Settings
REQUEST_DELAY=1.0
MAX_RETRIES=3
TIMEOUT=30
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

### 3. API Key Setup

#### Google Custom Search (Optional but Recommended)
1. Go to [Google Developers Console](https://console.developers.google.com/)
2. Create new project
3. Enable Custom Search API
4. Create credentials (API Key)
5. Set up Custom Search Engine at [Google CSE](https://cse.google.com/)

#### Semantic Scholar API (Optional)
1. Go to [Semantic Scholar API](https://www.semanticscholar.org/product/api)
2. Register for API key
3. Add to `.env` file

### 4. Project Structure Setup

```bash
# Create the complete directory structure
mkdir -p src/{agents,scrapers,processing,rag,workflows,utils}
mkdir -p tests
mkdir -p logs
mkdir -p data

# Create __init__.py files
touch src/__init__.py
touch src/agents/__init__.py
touch src/scrapers/__init__.py
touch src/processing/__init__.py
touch src/rag/__init__.py
touch src/workflows/__init__.py
touch src/utils/__init__.py
```

## 🔧 Running the System

### Method 1: Development Mode

```bash
# Terminal 1: Start FastAPI backend
python main.py

# Terminal 2: Start Streamlit frontend
streamlit run streamlit_app.py
```

### Method 2: Production Mode with Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501

# Start both services
CMD ["sh", "-c", "python main.py & streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  research-assistant:
    build: .
    ports:
      - "8000:8000"  # FastAPI
      - "8501:8501"  # Streamlit
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GOOGLE_CSE_ID=${GOOGLE_CSE_ID}
    volumes:
      - ./chroma_db:/app/chroma_db
      - ./logs:/app/logs
    restart: unless-stopped
```

Run with Docker:

```bash
docker-compose up -d
```

## 📖 Usage Guide

### Basic Research Workflow

1. **Access the Interface**
   - FastAPI docs: `http://localhost:8000/docs`
   - Streamlit UI: `http://localhost:8501`

2. **Start a Research Task**
   ```python
   # Via API
   import requests
   
   response = requests.post("http://localhost:8000/research", json={
       "query": "transformer architecture in natural language processing",
       "max_papers": 50,
       "include_analysis": True
   })
   
   request_id = response.json()["request_id"]
   ```

3. **Monitor Progress**
   ```python
   # Check status
   status = requests.get(f"http://localhost:8000/research/{request_id}/status")
   print(status.json())
   ```

4. **Get Results**
   ```python
   # Get complete results
   results = requests.get(f"http://localhost:8000/research/{request_id}/results")
   synthesis = results.json()["synthesis"]
   ```

### Advanced Features

#### Custom Paper Processing
```python
from src.processing.pdf_processor import PDFProcessor
from src.utils.config import config

async def process_custom_pdf():
    async with PDFProcessor(config) as processor:
        content = await processor.process_pdf_from_url("https://arxiv.org/pdf/1706.03762.pdf")
        print(f"Extracted {len(content.text)} characters")
        print(f"Found {len(content.sections)} sections")
```

#### Direct Vector Search
```python
from src.knowledge.vector_store import VectorStoreManager

async def search_knowledge_base():
    vector_store = VectorStoreManager(config)
    await vector_store.initialize()
    
    results = await vector_store.similarity_search("attention mechanism", k=10)
    for doc in results:
        print(f"Title: {doc.metadata.get('title')}")
        print(f"Content: {doc.page_content[:200]}...")
```

#### Custom Synthesis
```python
from src.agents.synthesis_agent import SynthesisAgent

async def custom_synthesis():
    agent = SynthesisAgent(config)
    
    # Your paper data
    papers = [...]  # List of paper dictionaries
    contents = [...]  # List of extracted content
    
    synthesis = await agent.synthesize_research(
        query="your research question",
        papers=papers,
        contents=contents
    )
    
    print(synthesis["summary"])
```

## 🔍 API Endpoints

### Research Endpoints
- `POST /research` - Start research task
- `GET /research/{id}/status` - Check task status
- `GET /research/{id}/results` - Get completed results

### Knowledge Base Endpoints
- `GET /search?query=...&k=10` - Search documents
- `GET /statistics` - Get database statistics
- `GET /clusters?query=...&k=20` - Find research clusters

### System Endpoints
- `GET /` - Health check
- `GET /docs` - API documentation

## 🛠️ Customization Options

### Adding New Data Sources

1. **Create New Scraper**
```python
# src/scrapers/new_source_scraper.py
class NewSourceScraper:
    async def search_papers(self, query: str) -> List[Paper]:
        # Implement scraping logic
        pass
```

2. **Integrate with Discovery Agent**
```python
# In src/agents/discovery_agent.py
async def search_papers(self, query: str, max_results: int = None):
    tasks = [
        self.search_arxiv(query, max_results // 4),
        self.search_semantic_scholar(query, max_results // 4),
        self.search_google_scholar(query, max_results // 4),
        self.search_new_source(query, max_results // 4),  # Add new source
    ]
```

### Custom Processing Pipeline

```python
# Custom workflow node
async def custom_analysis_node(self, state: ResearchState) -> ResearchState:
    # Your custom analysis logic
    state["custom_analysis"] = "Your analysis results"
    return state

# Add to workflow
workflow.add_node("custom_analysis", self.custom_analysis_node)
workflow.add_edge("synthesize_results", "custom_analysis")
```

### UI Customization

Modify `streamlit_app.py` to add new features:

```python
def custom_analysis_page():
    st.header("🔬 Custom Analysis")
    
    # Your custom Streamlit components
    analysis_type = st.selectbox("Analysis Type", ["Trend", "Network", "Topic"])
    
    if st.button("Run Analysis"):
        # Call your custom analysis
        pass
```

## 📊 Performance Optimization

### Caching Strategies

```python
# Add Redis for production caching
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Cache search results
def cache_search_results(query: str, results: List[Paper]):
    cache_key = f"search:{hash(query)}"
    redis_client.setex(cache_key, 3600, json.dumps([asdict(p) for p in results]))
```

### Batch Processing

```python
# Process multiple queries in batch
async def batch_research(queries: List[str]):
    tasks = [workflow.run_research(query) for query in queries]
    results = await asyncio.gather(*tasks)
    return results
```

### Database Optimization

```python
# Optimize ChromaDB collection
collection = chroma_client.create_collection(
    name="research_papers_optimized",
    metadata={
        "hnsw:space": "cosine",
        "hnsw:construction_ef": 200,
        "hnsw:M": 16
    }
)
```

## 🐛 Troubleshooting

### Common Issues

1. **OCR Not Working**
   ```bash
   # Install Tesseract properly
   which tesseract
   tesseract --version
   ```

2. **ChromaDB Permission Issues**
   ```bash
   # Fix permissions
   chmod -R 755 ./chroma_db
   ```

3. **API Rate Limits**
   ```python
   # Increase delays in config
   REQUEST_DELAY=2.0
   MAX_RETRIES=5
   ```

4. **Memory Issues**
   ```python
   # Reduce batch sizes
   MAX_PAPERS_PER_SEARCH=25
   CHUNK_SIZE=500
   ```

### Logging and Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Monitor workflow state
def debug_workflow_state(state: ResearchState):
    logger.debug(f"Current step: {state['current_step']}")
    logger.debug(f"Papers found: {len(state['papers'])}")
    logger.debug(f"Errors: {state['errors']}")
```

## 🚀 Production Deployment

### Scalability Considerations

1. **Use Redis for session storage**
2. **Implement proper async queuing (Celery)**
3. **Add load balancing (Nginx)**
4. **Monitor with Prometheus/Grafana**
5. **Use managed vector database (Pinecone/Weaviate)**
