# Academic Research Assistant

An intelligent research platform that leverages AI agents and vector search to discover, analyze, and synthesize academic literature. This system provides comprehensive research assistance through automated paper discovery, content extraction, and intelligent analysis.

## 🌟 Features

- **Intelligent Paper Discovery**: Automated search across multiple academic databases
- **Smart Content Extraction**: AI-powered extraction from both text-based and scanned PDF papers
- **Comprehensive Analysis**: 9-point research analysis covering trends, gaps, and methodologies
- **Vector-Based Search**: Semantic similarity search using embeddings
- **Multi-Agent Architecture**: Specialized AI agents for discovery, extraction, and synthesis
- **Caching System**: Efficient session management and result caching

## 🏗️ Architecture

### System Components

#### Frontend
- **Framework**: Flask web application
- **Features**: Research query submission and result visualization

#### Backend 
- **Framework**: FastAPI for high-performance data processing
- **Orchestration**: LangGraph-based workflow management

#### Data Storage
- **Vector Database**: Chroma for embedding storage and similarity search
- **Cache**: Redis for session management and temporary data storage
- **Document Processing**: Support for text-based and OCR-scanned PDFs

#### External Integrations
- **Google Scholar**: Academic paper discovery
- **Semantic Scholar**: Enhanced metadata and citation analysis
- **ArXiv**: Preprint repository access

### Workflow Process

1. **Query Submission**: User submits research query through frontend
2. **Knowledge Base Check**: System searches existing documents in vector store
3. **Conditional Discovery**: 
   - If sufficient documents found (≥ threshold): Proceed to synthesis
   - If insufficient documents: Trigger discovery agent
4. **Paper Discovery**: Multi-source search across academic databases
5. **Content Extraction**: AI-powered extraction of structured content
6. **Synthesis & Analysis**: Comprehensive 9-point analysis generation
7. **Report Generation**: Final research report compilation

## 🤖 AI Agents

### Discovery Agent
- **Purpose**: Find relevant academic papers across multiple sources
- **Capabilities**: 
  - Multi-database search coordination
  - Relevance scoring and filtering
  - Metadata extraction

### Extract Agent
- **Purpose**: Process and structure document content
- **Capabilities**:
  - PDF text extraction (text-based and OCR)
  - Content structuring and cleaning
  - Key information identification

### Synthesis Agent
- **Purpose**: Generate comprehensive research analysis
- **Capabilities**:
  - 9-point analytical framework
  - Trend identification
  - Gap analysis
  - Methodology assessment

## 📊 Analysis Framework

The system provides a comprehensive 9-point analysis for each research topic:

1. **Knowledge Base Search**: Search and extract from existing PDF content
2. **Online Paper Discovery**: Identify relevant research papers
3. **Theme Identification**: Extract main research themes
4. **Activity Analysis**: Assess research field maturity and activity levels
5. **Challenge Extraction**: Identify key research challenges
6. **Gap Analysis**: Discover research opportunities
7. **Methodology Trends**: Analyze methodological approaches
8. **Citation Analysis**: Highlight top-cited papers
9. **Temporal Analysis**: Track research trends over time

## 🚀 Getting Started

### Prerequisites

```bash
Python 3.8+
Redis server
Node.js (for frontend)
```

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/your-username/academic-research-assistant.git
cd academic-research-assistant
```

2. **Backend Setup**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys and configuration
```

3. **Frontend Setup**
```bash
cd frontend
npm install
npm run build
```

4. **Start Services**
```bash
# Start Redis
redis-server

# Start Flask backend
python app.py

# Start frontend (if separate)
cd frontend && npm start
```

### Configuration

Create a `.env` file with the following variables:

```env
# API Keys
GOOGLE_SCHOLAR_API_KEY=your_api_key
SEMANTIC_SCHOLAR_API_KEY=your_api_key

# Database Configuration
REDIS_URL=redis://localhost:6379
CHROMA_PERSIST_DIRECTORY=./chroma_db

# Agent Configuration
DISCOVERY_THRESHOLD=5
MAX_PAPERS_PER_QUERY=50

```

## 📋 Usage

### Basic Research Query

```python
from research_assistant import ResearchAssistant

# Initialize the assistant
assistant = ResearchAssistant()

# Submit a research query
query = "machine learning in healthcare"
results = assistant.process_query(query)

# Access analysis results
themes = results.themes
challenges = results.challenges
recommendations = results.recommendations
```

### API Endpoints

#### Submit Research Query
```http
POST /api/research
Content-Type: application/json

{
  "query": "your research topic",
  "max_papers": 50,
  "include_preprints": true
}
```

#### Get Analysis Results
```http
GET /api/research/{query_id}/results
```

#### Upload PDF Documents
```http
POST /api/documents/upload
Content-Type: multipart/form-data

{
  "files": [pdf_files],
  "category": "research_papers"
}
```

## 🔧 Technical Details

### Vector Search
- **Embedding Model**: Sentence transformers for semantic similarity
- **Similarity Threshold**: Configurable relevance scoring
- **Index Management**: Automatic embedding generation and storage

### Document Processing
- **Text Extraction**: Pymupdf for text-based PDFs
- **OCR Processing**: Tesseract for scanned documents
- **Html Processing**: BeautifulSoup for html bsed web content extract
- **Content Cleaning**: Automated formatting and structure detection

### Agent Coordination
- **Framework**: LangGraph for workflow orchestration
- **State Management**: Persistent workflow state tracking
- **Error Handling**: Robust fallback mechanisms

## 📈 Performance

### Optimization Features
- **Parallel Processing**: Multi-threaded document processing
- **Caching Strategy**: Redis-based result caching
- **Batch Operations**: Efficient bulk document processing
- **Rate Limiting**: Respectful API usage patterns

### Benchmarks
- **Query Processing**: < 30 seconds for typical queries
- **Document Indexing**: ~1000 papers/minute
- **Memory Usage**: < 2GB for 10,000 document corpus


## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Note**: This system is designed for academic research purposes. Please ensure compliance with the terms of service of accessed academic databases and respect copyright regulations when using extracted content.