from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional, Callable
from dataclasses import asdict
import logging
import asyncio

from src.agents.discovery_agent import DiscoveryAgent
from src.processing.pdf_processor import PDFProcessor
from src.agents.synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)

# State management for the workflow
class ResearchState(TypedDict):
    query: str
    papers: List[Dict]
    web_extracted_contents: List[Dict]
    synthesis_result: Optional[Dict]
    knowledge_graph_updated: bool
    current_step: str
    errors: List[str]
    metadata: Dict[str, Any]
    skip_discovery: bool
    progress: int
    progress_callback: Optional[Callable]

class ResearchWorkflow:
    """LangGraph-based multi-agent research workflow"""
    
    def __init__(self, config, vector_store):
        self.config = config
        self.discovery_agent = None
        self.pdf_processor = None
        self.vector_store = vector_store
        self.synthesis_agent = None
        self.workflow = None
        
        # Define progress steps and their weights
        self.progress_steps = {
            "checking_existing_docs": 10,
            "discovering_papers": 25,
            "extracting_content": 45,
            "updating_knowledge_graph": 60,
            "synthesizing_results": 80,
            "quality_check": 100
        }
        
    async def initialize(self):
        """Initialize all agents and components"""

        self.pdf_processor = PDFProcessor(self.config)
        self.discovery_agent = DiscoveryAgent(self.config, self.vector_store)
        self.synthesis_agent = SynthesisAgent(self.config)
        
        
        # Build the workflow graph
        self.workflow = self.build_workflow()
        
    async def cleanup(self):
        """Cleanup resources"""
        if self.vector_store:
            await self.vector_store.close()
    
    async def update_progress(self, state: ResearchState, step: str):
        """Update progress and call callback if available"""
        progress = self.progress_steps.get(step, state.get("progress", 0))
        state["progress"] = progress
        
        if state.get("progress_callback"):
            try:
                await state["progress_callback"](progress, step)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow"""
        
        # Define the workflow graph
        workflow = StateGraph(ResearchState)
        
        # Add nodes (agents)
        workflow.add_node("check_existing_docs", self.check_existing_docs_node)
        workflow.add_node("discover_papers", self.discover_papers_node)
        workflow.add_node("extract_content", self.extract_content_node)
        workflow.add_node("update_knowledge_graph", self.update_knowledge_graph_node)
        workflow.add_node("synthesize_results", self.synthesize_results_node)
        workflow.add_node("quality_check", self.quality_check_node)
        
        # Define the workflow edges
        workflow.set_entry_point("check_existing_docs")
        
        # Linear workflow with conditional branches
        workflow.add_edge("discover_papers", "extract_content")
        workflow.add_edge("extract_content", "update_knowledge_graph")
        workflow.add_edge("update_knowledge_graph", "synthesize_results")
        workflow.add_edge("synthesize_results", "quality_check")
        
        # Conditional ending
        workflow.add_conditional_edges(
            "quality_check",
            self.should_continue,
            {
                "continue": "discover_papers",
                "end": END
            }
        )

        workflow.add_conditional_edges(
            "check_existing_docs",
            self.should_discover_papers,
            {
                "discover": "discover_papers",
                "skip_to_synthesis": "synthesize_results" 
            }
        )
        
        return workflow.compile()
    

    def should_discover_papers(self, state: ResearchState) -> str:
        """Decide whether to discover papers or skip to synthesis"""
        if state.get("skip_discovery", False):
            return "skip_to_synthesis"
        else:
            return "discover"
        
    async def check_existing_docs_node(self, state: ResearchState) -> ResearchState:
        """Check if we have enough existing documents before discovering new ones"""
        try:
            state["current_step"] = "checking_existing_docs"
            await self.update_progress(state, "checking_existing_docs")
            logger.info(f"Checking existing documents for query: {state['query']}")

            await asyncio.sleep(5)
            
            # Filter by relevance score if available
            docs_with_scores = await self.vector_store.similarity_search_with_scores(
                query=state["query"],
                k=50
            )
            # Keep docs with score above threshold
            relevant_docs = [doc for doc, score in docs_with_scores if score > 0.8]
                        
            # Convert existing docs to paper format for synthesis
            existing_papers = []
            for doc in relevant_docs:
                paper_dict = {
                    "title": doc.metadata.get("title", "Existing Document"),
                    "url": doc.metadata.get("paper_id", ""),
                    "publication_date": doc.metadata.get("pub_date", ""),
                    "venue": doc.metadata.get("venue", ""),
                    "authors": doc.metadata.get("authors", []),
                    "citations": doc.metadata.get("citations", 0),
                    "doi": doc.metadata.get("doi",""),
                    "sections": doc.metadata.get("sections","").split(","),
                    "references": doc.metadata.get("references","").split(","),
                    "abstract": doc.page_content,
                    "text": doc.metadata.get("full_text", ""),
                }
                existing_papers.append(paper_dict)

            unique_papers_count = len(set(
                paper.get("url", "")
                for paper in existing_papers 
                if paper.get("url")
            ))

            state["skip_discovery"] = unique_papers_count >= int(self.config.max_papers_per_search ) + 10

            if state["skip_discovery"]:
                logger.info(f"Found {unique_papers_count} existing relevant papers, skipping discovery")
                state["papers"] = existing_papers
                state["metadata"]["used_existing_docs"] = True
                state["metadata"]["papers_found"] = unique_papers_count
            else:
                logger.info(f"Found only {unique_papers_count} existing papers, will discover new papers")
                state["metadata"]["used_existing_docs"] = False
            
            return state
            
        except Exception as e:
            error_msg = f"Error in check_existing_docs_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            # Default to discovery on error
            state["skip_discovery"] = False
            return state
    
    async def discover_papers_node(self, state: ResearchState) -> ResearchState:
        """Node for discovering papers"""
        try:
            state["current_step"] = "discovering_papers"
            await self.update_progress(state, "discovering_papers")
            logger.info(f"Discovering papers for query: {state['query']}")

            async with self.discovery_agent as agent:
                papers = await agent.search_papers(
                    state["query"],
                    max_results=self.config.max_papers_per_search
                )
            
            # Convert papers to serializable format
            serializable_papers = []
            for paper in papers:
                paper_dict = asdict(paper)
                # Handle datetime serialization
                if paper_dict.get('publication_date'):
                    paper_dict['publication_date'] = paper_dict['publication_date'].isoformat()
                serializable_papers.append(paper_dict)
            
            state["web_extracted_contents"] = serializable_papers
            return state
            
        except Exception as e:
            error_msg = f"Error in discover_papers_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    async def extract_content_node(self, state: ResearchState) -> ResearchState:
        """Node for extracting content from papers"""
        try:
            # Skip content extraction if using existing docs
            if state.get("metadata", {}).get("used_existing_docs", False):
                logger.info("Using existing documents, skipping content extraction")
                state["web_extracted_contents"] = []
                return state
            state["current_step"] = "extracting_content"
            await self.update_progress(state, "extracting_content")
            logger.info("Extracting content from papers")
            
            web_extracted_contents = []
            successful_extractions = 0
            total_papers = len(state["web_extracted_contents"])
            
            async with self.pdf_processor as processor:
                for i, paper_dict in enumerate(state["web_extracted_contents"]):
                    if paper_dict.get("url"):
                        try:
                            content = await processor.process_pdf_from_url(paper_dict["url"])
                            if content:
                                # Convert to serializable format
                                content_dict = asdict(content)
                                content_dict["url"] = paper_dict.get("url", "")
                                content_dict["title"] = paper_dict.get("title", "")
                                content_dict["authors"] = paper_dict.get("authors", [])
                                content_dict["publication_date"] = paper_dict.get("publication_date","")
                                content_dict["venue"] = paper_dict.get("venue", "")
                                content_dict["doi"] = paper_dict.get("doi", "")
                                content_dict["citations"] = paper_dict.get("citations", 0)
                                content_dict["abstract"] = paper_dict.get("abstract", "")
                                web_extracted_contents.append(content_dict)
                                successful_extractions += 1
                                
                                # Update sub-progress during content extraction
                                if state.get("progress_callback") and total_papers > 0:
                                    sub_progress = 20 + (20 * (i + 1) / total_papers) 
                                    await state["progress_callback"](int(sub_progress), f"extracting_content ({i+1}/{total_papers})")
                                
                                # Limit concurrent processing
                                if successful_extractions >= 100:
                                    break
                                    
                        except Exception as e:
                            logger.warning(f"Failed to extract content from {paper_dict.get('title', 'Unknown')}: {e}")
                            continue

            state["web_extracted_contents"] = web_extracted_contents            
            logger.info(f"Successfully extracted content from {len(web_extracted_contents)} papers")
            return state
            
        except Exception as e:
            error_msg = f"Error in extract_content_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    async def update_knowledge_graph_node(self, state: ResearchState) -> ResearchState:
        """Node for updating the knowledge graph"""
        try:
            # Skip if using existing docs
            if state.get("metadata", {}).get("used_existing_docs", False):
                logger.info("Using existing documents, skipping knowledge graph update")
                state["knowledge_graph_updated"] = True
                return state
            
            state["current_step"] = "updating_knowledge_graph"
            await self.update_progress(state, "updating_knowledge_graph")
            logger.info("Updating knowledge graph")
            
            total_contents = len(state["web_extracted_contents"])
            # Process each extracted contentpage_content 
            for i, content_dict in enumerate(state["web_extracted_contents"]):
                # Add to vector store
                await self.vector_store.add_document(
                    content=content_dict["abstract"],
                    metadata={
                        "title": content_dict.get("title", ""),
                        "paper_id": content_dict.get("url", ""),
                        "pub_date": content_dict.get("publication_date", ""),
                        "sections": ','.join(content_dict.get("sections", [])),
                        "citations": content_dict.get("citations", 0),
                        "venue": content_dict.get("venue", ""),
                        "authors": ','.join(content_dict.get("authors", [])),
                        "doi": content_dict.get("doi", ""),
                        "full_text": content_dict.get("text", ""),
                        "references": ','.join(content_dict.get("references", [])),
                        "extraction_method": content_dict.get("metadata", {}).get("extraction_method", "text")
                    }
                )
                
                # Update sub-progress during knowledge graph update
                if state.get("progress_callback") and total_contents > 0:
                    sub_progress = 40 + (20 * (i + 1) / total_contents)
                    await state["progress_callback"](int(sub_progress), f"updating_knowledge_graph ({i+1}/{total_contents})")
            
            state["knowledge_graph_updated"] = True
            state["metadata"]["documents_added"] = len(state["web_extracted_contents"])
            
            logger.info("Knowledge graph updated successfully")
            return state
            
        except Exception as e:
            error_msg = f"Error in update_knowledge_graph_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["knowledge_graph_updated"] = False
            return state
    
    async def synthesize_results_node(self, state: ResearchState) -> ResearchState:
        """Node for synthesizing research results"""
        try:
            state["current_step"] = "synthesizing_results"
            await self.update_progress(state, "synthesizing_results")
            logger.info("Synthesizing research results")
            
            if state.get("metadata", {}).get("used_existing_docs", True):
                # Generate synthesis for papers using the synthesis agent
                logger.info("synthetising from docs")
                synthesis_result = await self.synthesis_agent.synthesize_research(
                    query=state["query"],
                    papers=state["papers"],
                )
            
            else:
                # Generate synthesis for web contents using the synthesis agent
                logger.info("synthetising from web")

                synthesis_result = await self.synthesis_agent.synthesize_research(
                    query=state["query"],
                    papers=state["web_extracted_contents"],
                    is_web_extracted=True,
                )

            
            state["synthesis_result"] = synthesis_result
            state["metadata"]["synthesis_completed"] = True
            
            logger.info("Research synthesis completed")
            return state
            
        except Exception as e:
            error_msg = f"Error in synthesize_results_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    async def quality_check_node(self, state: ResearchState) -> ResearchState:
        """Node for quality checking results"""
        try:
            state["current_step"] = "quality_check"
            await self.update_progress(state, "quality_check")
            logger.info("Performing quality check")
            
            quality_score = 0
            quality_issues = []
            
            # Check quality
            if state.get("synthesis_result"):
                synthesis = state["synthesis_result"]
                if len(synthesis.get("summary", "")) > 50:
                    quality_score += 25
                if len(synthesis.get("key_findings", [])) > 3:
                    quality_score += 25
                if len(synthesis.get("methodology_trends", [])) > 3:
                    quality_score += 25
                if len(synthesis.get("future_directions", [])) > 5:
                    quality_score += 25
            else:
                quality_issues.append("No synthesis result")
            
            state["metadata"]["quality_score"] = quality_score
            state["metadata"]["quality_issues"] = quality_issues
            
            logger.info(f"Quality check completed. Score: {quality_score}/100")
            return state
            
        except Exception as e:
            error_msg = f"Error in quality_check_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    def should_continue(self, state: ResearchState) -> str:
        """Determine if workflow should continue or end"""
        quality_score = state["metadata"].get("quality_score", 0)
        
        # Continue if quality is too low and we haven't tried too many times
        retry_count = state["metadata"].get("retry_count", 0)
        
        if quality_score < 50 and retry_count < 2:
            state["metadata"]["retry_count"] = retry_count + 1
            return "continue"
        else:
            return "end"
    
    async def run_research(self, query: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Run the complete research workflow with optional progress callback"""
        
        # Initialize state
        initial_state = ResearchState(
            query=query,
            papers=[],
            web_extracted_contents=[],
            synthesis_result=None,
            knowledge_graph_updated=False,
            current_step="initialized",
            errors=[],
            metadata={"retry_count": 0},
            skip_discovery=False,
            progress=0,
            progress_callback=progress_callback
        )
        
        try:
            # Run the workflow
            final_state = await self.workflow.ainvoke(initial_state)
            
            # Final progress update
            if progress_callback:
                await progress_callback(100, "completed")

            # Format results
            results = {
                "query": query,
                "status": "completed" if not final_state.get("errors") else "completed_with_errors",
                "papers_found": final_state.get("metadata", {}).get("papers_found", 0),
                "content_extracted": len(final_state.get("web_extracted_contents", [])),
                "synthesis": final_state.get("synthesis_result"),
                "quality_score": final_state.get("metadata", {}).get("quality_score", 0),
                "errors": final_state.get("errors", []),
                "metadata": final_state.get("metadata", {}),
                "final_progress": final_state.get("progress", 100)
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            if progress_callback:
                await progress_callback(100, f"failed: {str(e)}")
            
            return {
                "query": query,
                "status": "failed",
                "error": str(e),
                "papers_found": 0,
                "content_extracted": 0,
                "synthesis": None,
                "quality_score": 0,
                "final_progress": 0
            }