from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import logging
from datetime import datetime
import uuid

from src.workflows.research_workflow import ResearchWorkflow
from src.utils.config import config
from src.rag.vector_store import VectorStoreManager
from src.utils.helpers import process_pdf_papers

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for request tracking
request_status = {}

# Initialize FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    global workflow_instance, vector_store_instance
    
    try:
        logger.info("Initializing Academic Research Assistant...")

        # Initialize vectorstore
        vector_store_instance = VectorStoreManager(config)
        await vector_store_instance.initialize()

        # Initialize workflow
        workflow_instance = ResearchWorkflow(config, vector_store_instance)
        await workflow_instance.initialize()

        logger.info("Application initialized successfully")
        yield 

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    finally:
        try:
            if workflow_instance:
                await workflow_instance.cleanup()

            if vector_store_instance:
                await vector_store_instance.close()

            logger.info("Application shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

app = FastAPI(title="Academic Research Assistant API",
    description="AI-powered academic research discovery and synthesis",
    version="1.0.0",
    lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "progress": 0,
        "current_step": "initializing",
        "query": request.query,
        "started_at": datetime.now().isoformat(),
    }
    
    # Start background task
    background_tasks.add_task(
        run_research_task, 
        request_id, 
        request.query
    )
    
    return {
        "request_id": request_id,
        "status": "started",
        "message": "Research task initiated"
    }

async def run_research_task(
    request_id: str, 
    query: str
):
    """Background task to run research workflow with detailed progress tracking"""
    
    async def progress_callback(progress: int, step: str):
        """Callback function to update progress"""
        try:
            # Update the request status with current progress
            request_status[request_id].update({
                "progress": progress,
                "current_step": step,
                "last_updated": datetime.now().isoformat()
            })
            logger.info(f"Research task {request_id}: {progress}% - {step}")
        except Exception as e:
            logger.warning(f"Failed to update progress for {request_id}: {e}")
    
    try:
        # Initial status update
        request_status[request_id].update({
            "status": "running",
            "started_at": datetime.now().isoformat()
        })
        
        # Run the research workflow with progress callback
        results = await workflow_instance.run_research(
            query=query,
            progress_callback=progress_callback
        )
        
        # Final status update with results
        request_status[request_id].update({
            "status": "completed",
            "progress": 100,
            "current_step": "completed",
            "results": results,
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"Research task {request_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Research task {request_id} failed: {e}")
        request_status[request_id].update({
            "status": "completed with errors",
            "progress": 100,
            "current_step": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/research/{request_id}/status")
def get_research_status(request_id: str):
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
    
@app.post("/update_knowledgebase", response_model=Dict[str, Any])
async def add_pdf_files_to_knowledgebase(data: Dict[str, str]):
    """
    Process uploaded PDF files and add them to the knowledge base
    
    Args:
        data: Dictionary containing upload_path and other parameters
        
    Returns:
        Dict containing processing results and statistics
    """
    try:
        # Validate input data
        upload_path = data.get("upload_path")
        if not upload_path:
            raise HTTPException(
                status_code=500,
                detail="upload_path is required"
            )
        
        logger.info(f"Starting knowledge base update with upload_path: {upload_path}")
        
        # Process PDF files
        try:
            # Call the async processing function
            results = await process_pdf_papers(config, vector_store_instance, upload_path)
            
            # Log results
            logger.info(f"Processing completed: {results['success_count']} successful, {results['error_count']} errors")
            
            # Determine response status
            if results["error_count"] == 0:
                status = "success"
                message = f"Successfully processed {results['success_count']} PDF files"
            elif results["success_count"] == 0:
                status = "error" 
                message = f"Failed to process all {results['error_count']} PDF files"
            else:
                status = "partial_success"
                message = f"Processed {results['success_count']} files successfully, {results['error_count']} failed"
            
            return {
                "status": status,
                "message": message,
                "upload_path": upload_path,
                "processed_count": results["success_count"],
                "error_count": results["error_count"],
                "files_processed": results["processed_files"],
                "errors": results["errors"],
            }
            
        except Exception as processing_error:
            logger.error(f"Error during PDF processing: {str(processing_error)}")
            raise HTTPException(
                status_code=400,
                detail=f"Error processing PDF files: {str(processing_error)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in add_pdf_files_to_knowledgebase: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

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
async def get_research_clusters():
    """Get research clusters for a query"""
    
    try:
        research_trends = await vector_store_instance.find_research_trends(workflow_instance.synthesis_agent)
        logger.info(f"trends extracted {research_trends}")

        return research_trends
        
    except Exception as e:
        logger.error(f"Clustering error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
