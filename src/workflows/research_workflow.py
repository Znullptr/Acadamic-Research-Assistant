# src/workflows/research_workflow.py
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional
import asyncio
from dataclasses import asdict
import logging

from src.agents.discovery_agent import DiscoveryAgent, Paper
from src.processing.pdf_processor import PDFProcessor, ExtractedContent
from src.rag.vector_store import VectorStoreManager
from src.agents.synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)

# State management for the workflow
class ResearchState(TypedDict):
    query: str
    papers: List[Dict]  # Serializable paper data
    extracted_contents: List[Dict]  # Serializable content data
    synthesis_result: Optional[Dict]
    knowledge_graph_updated: bool
    current_step: str
    errors: List[str]
    metadata: Dict[str, Any]

class ResearchWorkflow:
    """LangGraph-based multi-agent research workflow"""
    
    def __init__(self, config):
        self.config = config
        self.discovery_agent = None
        self.pdf_processor = None
        self.vector_store = None
        self.synthesis_agent = None
        self.workflow = None
        
    async def initialize(self):
        """Initialize all agents and components"""
        self.discovery_agent = DiscoveryAgent(self.config)
        self.pdf_processor = PDFProcessor(self.config)
        self.vector_store = VectorStoreManager(self.config)
        self.synthesis_agent = SynthesisAgent(self.config)
        
        await self.vector_store.initialize()
        
        # Build the workflow graph
        self.workflow = self.build_workflow()
        
    async def cleanup(self):
        """Cleanup resources"""
        if self.vector_store:
            await self.vector_store.close()
    
    def build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow"""
        
        # Define the workflow graph
        workflow = StateGraph(ResearchState)
        
        # Add nodes (agents)
        workflow.add_node("discover_papers", self.discover_papers_node)
        workflow.add_node("extract_content", self.extract_content_node)
        workflow.add_node("update_knowledge_graph", self.update_knowledge_graph_node)
        workflow.add_node("synthesize_results", self.synthesize_results_node)
        workflow.add_node("quality_check", self.quality_check_node)
        
        # Define the workflow edges
        workflow.set_entry_point("discover_papers")
        
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
                "continue": "discover_papers",  # Loop back for more papers
                "end": END
            }
        )
        
        return workflow.compile()
    
    async def discover_papers_node(self, state: ResearchState) -> ResearchState:
        """Node for discovering papers"""
        try:
            state["current_step"] = "discovering_papers"
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
            
            state["papers"] = serializable_papers
            state["metadata"]["papers_found"] = len(papers)
            
            logger.info(f"Found {len(papers)} papers")
            return state
            
        except Exception as e:
            error_msg = f"Error in discover_papers_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    async def extract_content_node(self, state: ResearchState) -> ResearchState:
        """Node for extracting content from papers"""
        try:
            state["current_step"] = "extracting_content"
            logger.info("Extracting content from papers")
            
            extracted_contents = []
            successful_extractions = 0
            
            async with self.pdf_processor as processor:
                for paper_dict in state["papers"]:
                    if paper_dict.get("pdf_url"):
                        try:
                            content = await processor.process_pdf_from_url(paper_dict["pdf_url"])
                            if content:
                                # Convert to serializable format
                                content_dict = asdict(content)
                                content_dict["paper_id"] = paper_dict.get("url", "")
                                content_dict["paper_title"] = paper_dict.get("title", "")
                                extracted_contents.append(content_dict)
                                successful_extractions += 1
                                
                                # Limit concurrent processing
                                if successful_extractions >= 10:
                                    break
                                    
                        except Exception as e:
                            logger.warning(f"Failed to extract content from {paper_dict.get('title', 'Unknown')}: {e}")
                            continue
            
            state["extracted_contents"] = extracted_contents
            state["metadata"]["content_extracted"] = len(extracted_contents)
            
            logger.info(f"Successfully extracted content from {len(extracted_contents)} papers")
            return state
            
        except Exception as e:
            error_msg = f"Error in extract_content_node: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            return state
    
    async def update_knowledge_graph_node(self, state: ResearchState) -> ResearchState:
        """Node for updating the knowledge graph"""
        try:
            state["current_step"] = "updating_knowledge_graph"
            logger.info("Updating knowledge graph")
            
            # Process each extracted content
            for content_dict in state["extracted_contents"]:
                # Add to vector store
                await self.vector_store.add_document(
                    content=content_dict["text"],
                    metadata={
                        "title": content_dict.get("paper_title", ""),
                        "paper_id": content_dict.get("paper_id", ""),
                        "sections": len(content_dict.get("sections", [])),
                        "references": len(content_dict.get("references", [])),
                        "extraction_method": content_dict.get("metadata", {}).get("extraction_method", "text")
                    }
                )
                # Process sections separately for better granularity
                for section in content_dict.get("sections", []):
                    if section.get("content") and len(section["content"]) > 100:
                        await self.vector_store.add_document(
                            content=section["content"],
                            metadata={
                                "title": content_dict.get("paper_title", ""),
                                "section_title": section.get("title", ""),
                                "paper_id": content_dict.get("paper_id", ""),
                                "type": "section"
                            }
                        )
            
            state["knowledge_graph_updated"] = True
            state["metadata"]["documents_added"] = len(state["extracted_contents"])
            
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
            logger.info("Synthesizing research results")
            
            # Prepare data for synthesis
            synthesis_data = {
                "query": state["query"],
                "papers": state["papers"],
                "extracted_contents": state["extracted_contents"],
                "total_papers": len(state["papers"]),
                "total_content": len(state["extracted_contents"])
            }
            
            # Generate synthesis using the synthesis agent
            synthesis_result = await self.synthesis_agent.synthesize_research(
                query=state["query"],
                papers=state["papers"],
                contents=state["extracted_contents"],
                vector_store=self.vector_store
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
            logger.info("Performing quality check")
            
            quality_score = 0
            quality_issues = []
            
            # Check paper quality
            if len(state["papers"]) < 5:
                quality_issues.append("Insufficient number of papers found")
            else:
                quality_score += 25
            
            # Check content extraction quality
            extraction_ratio = len(state["extracted_contents"]) / max(len(state["papers"]), 1)
            if extraction_ratio < 0.3:
                quality_issues.append("Low content extraction rate")
            else:
                quality_score += 25
            
            # Check synthesis quality
            if state.get("synthesis_result"):
                synthesis = state["synthesis_result"]
                if len(synthesis.get("summary", "")) > 200:
                    quality_score += 25
                if len(synthesis.get("key_findings", [])) > 3:
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
    
    async def run_research(self, query: str) -> Dict[str, Any]:
        """Run the complete research workflow"""
        
        # Initialize state
        initial_state = ResearchState(
            query=query,
            papers=[],
            extracted_contents=[],
            synthesis_result=None,
            knowledge_graph_updated=False,
            current_step="initialized",
            errors=[],
            metadata={"retry_count": 0}
        )
        
        try:
            # Run the workflow
            final_state = await self.workflow.ainvoke(initial_state)
            
            # Format results
            results = {
                "query": query,
                "status": "completed" if not final_state.get("errors") else "completed_with_errors",
                "papers_found": len(final_state.get("papers", [])),
                "content_extracted": len(final_state.get("extracted_contents", [])),
                "synthesis": final_state.get("synthesis_result"),
                "quality_score": final_state.get("metadata", {}).get("quality_score", 0),
                "errors": final_state.get("errors", []),
                "metadata": final_state.get("metadata", {})
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            return {
                "query": query,
                "status": "failed",
                "error": str(e),
                "papers_found": 0,
                "content_extracted": 0,
                "synthesis": None,
                "quality_score": 0
            }
