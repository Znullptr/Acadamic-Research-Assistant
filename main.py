from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime
import uuid

from src.workflows.research_workflow import ResearchWorkflow
from src.utils.config import config
from src.rag.vector_store import VectorStoreManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Academic Research Assistant API",
    description="AI-powered academic research discovery and synthesis",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global workflow instance
workflow_instance = None
vector_store_instance = None

# Request/Response models
class ResearchRequest(BaseModel):
    query: str
    max_papers: Optional[int] = 50
    include_analysis: bool = True

class ResearchResponse(BaseModel):
    request_id: str
    status: str
    query: str
    papers_found: int
    content_extracted: int
    synthesis: Optional[Dict[str, Any]]
    quality_score: int
    errors: List[str]
    metadata: Dict[str, Any]
    timestamp: str

class StatusResponse(BaseModel):
    status: str
    message: str
    timestamp: str

# In-memory storage for request tracking (use Redis in production)
request_status = {}

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    global workflow_instance, vector_store_instance
    
    try:
        logger.info("Initializing Academic Research Assistant...")
        
        # Initialize workflow
        workflow_instance = ResearchWorkflow(config)
        await workflow_instance.initialize()
        
        # Initialize vector store for direct access
        vector_store_instance = VectorStoreManager(config)
        await vector_store_instance.initialize()
        
        logger.info("Application initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global workflow_instance, vector_store_instance
    
    try:
        if workflow_instance:
            await workflow_instance.cleanup()
        
        if vector_store_instance:
            await vector_store_instance.close()
            
        logger.info("Application shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@app.get("/", response_model=StatusResponse)
async def root():
    """Health check endpoint"""
    return StatusResponse(
        status="healthy",
        message="Academic Research Assistant API is running",
        timestamp=datetime.now().isoformat()
    )

@app.post("/research", response_model=Dict[str, str])
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start a research task"""
    
    request_id = str(uuid.uuid4())
    
    # Initialize request status
    request_status[request_id] = {
        "status": "started",
        "query": request.query,
        "started_at": datetime.now().isoformat(),
        "progress": "initializing"
    }
    
    # Start background task
    background_tasks.add_task(
        run_research_task, 
        request_id, 
        request.query, 
        request.max_papers,
        request.include_analysis
    )
    
    return {
        "request_id": request_id,
        "status": "started",
        "message": "Research task initiated"
    }

async def run_research_task(
    request_id: str, 
    query: str, 
    max_papers: int,
    include_analysis: bool
):
    """Background task to run research workflow"""
    
    try:
        # Update status
        request_status[request_id]["status"] = "running"
        request_status[request_id]["progress"] = "discovering papers"
        
        # Run the research workflow
        results = await workflow_instance.run_research(query)
        
        # Update status with results
        request_status[request_id].update({
            "status": "completed",
            "progress": "finished",
            "results": results,
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"Research task {request_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Research task {request_id} failed: {e}")
        request_status[request_id].update({
            "status": "failed",
            "progress": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/research/{request_id}/status")
async def get_research_status(request_id: str):
    """Get status of a research task"""
    
    if request_id not in request_status:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return request_status[request_id]

@app.get("/research/{request_id}/results", response_model=ResearchResponse)
async def get_research_results(request_id: str):
    """Get results of a completed research task"""
    
    if request_id not in request_status:
        raise HTTPException(status_code=404, detail="Request not found")
    
    task_status = request_status[request_id]
    
    if task_status["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Task not completed. Status: {task_status['status']}"
        )
    
    results = task_status["results"]
    
    return ResearchResponse(
        request_id=request_id,
        status=results["status"],
        query=results["query"],
        papers_found=results["papers_found"],
        content_extracted=results["content_extracted"],
        synthesis=results["synthesis"],
        quality_score=results["quality_score"],
        errors=results["errors"],
        metadata=results["metadata"],
        timestamp=task_status["completed_at"]
    )

@app.get("/search")
async def search_knowledge_base(query: str, k: int = 10):
    """Search the knowledge base"""
    
    try:
        results = await vector_store_instance.similarity_search(query, k=k)
        
        return {
            "query": query,
            "results": [
                {
                    "content": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in results
            ]
        }
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/statistics")
async def get_statistics():
    """Get knowledge base statistics"""
    
    try:
        stats = await vector_store_instance.get_document_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/clusters")
async def get_research_clusters(query: str, k: int = 20):
    """Get research clusters for a query"""
    
    try:
        clusters = await vector_store_instance.find_research_clusters(query, k=k)
        return clusters
        
    except Exception as e:
        logger.error(f"Clustering error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
