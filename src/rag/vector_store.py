from typing import List, Dict, Any, Optional, Tuple
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import chromadb
from chromadb.config import Settings
import asyncio
import logging
import uuid
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """Manages vector store operations and knowledge graph functionality"""
    
    def __init__(self, config):
        self.config = config
        self.embeddings = None
        self.vectorstore = None
        self.chroma_client = None
        self.collection = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
    async def initialize(self):
        """Initialize the vector store and embeddings"""
        try:
            # Initialize embeddings
            self.embeddings = GoogleGenerativeAIEmbeddings(
                google_api_key=self.config.google_api_key,
                model="models/embedding-001"
            )
            
            # Ensure the database directory exists
            db_path = Path(self.config.chroma_db_path)
            db_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize ChromaDB client
            self.chroma_client = chromadb.PersistentClient(
                path=str(db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            collection_name = "research_papers"
            try:
                self.collection = self.chroma_client.get_collection(collection_name)
                logger.info(f"Loaded existing collection: {collection_name}")
            except:
                self.collection = self.chroma_client.create_collection(
                    name=collection_name,
                    metadata={"description": "Academic research papers collection"}
                )
                logger.info(f"Created new collection: {collection_name}")
            
            # Initialize Langchain ChromaDB wrapper
            self.vectorstore = Chroma(
                client=self.chroma_client,
                collection_name=collection_name,
                embedding_function=self.embeddings
            )
            
            logger.info("Vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
            raise
    
    async def add_document(
        self, 
        content: str, 
        metadata: Dict[str, Any],
        chunk_content: bool = True
    ) -> List[str]:
        """Add a document to the vector store"""
        try:
            if not content or not content.strip():
                logger.warning("Empty content provided, skipping")
                return []
            
            # Prepare metadata with required fields
            doc_metadata = {
                "timestamp": datetime.now().isoformat(),
                "content_length": len(content),
                **metadata
            }
            # Clean and prepare content
            cleaned_content = self.clean_content(content)
            
            if chunk_content and len(cleaned_content) > self.config.chunk_size:
                # Split content into chunks
                texts = self.text_splitter.split_text(cleaned_content)
                documents = []
                
                for i, text in enumerate(texts):
                    chunk_metadata = doc_metadata.copy()
                    chunk_metadata.update({
                        "chunk_index": i,
                        "total_chunks": len(texts),
                        "chunk_id": f"{metadata.get('paper_id', 'unknown')}_{i}"
                    })
                    
                    documents.append(Document(
                        page_content=text,
                        metadata=chunk_metadata
                    ))
            else:
                # Add as single document
                documents = [Document(
                    page_content=cleaned_content,
                    metadata=doc_metadata
                )]
            # Add to vector store
            doc_ids = await self.add_documents(documents)
            logger.info(f"Added {len(documents)} document chunks to vector store")
            return doc_ids
            
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return []
    
    async def add_documents(self, documents: List[Document]) -> List[str]:
        """Add multiple documents to the vector store"""
        try:
            # Generate unique IDs for documents
            doc_ids = [str(uuid.uuid4()) for _ in documents]
            await self.vectorstore.aadd_documents(documents=documents, ids=doc_ids)
            
            return doc_ids
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return []
    
    async def similarity_search(
        self, 
        query: str, 
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """Perform similarity search"""
        try:
            # Prepare search kwargs
            search_kwargs = {"k": k}
            if filter_metadata:
                search_kwargs["filter"] = filter_metadata
            
            # Perform search
            results = await asyncio.to_thread(
                self.vectorstore.similarity_search,
                query,
                **search_kwargs
            )
            
            logger.info(f"Found {len(results)} similar documents for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            return []
    
    async def similarity_search_with_scores(
        self, 
        query: str, 
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Document, float]]:
        """Perform similarity search with relevance scores"""
        try:
            search_kwargs = {"k": k}
            if filter_metadata:
                search_kwargs["filter"] = filter_metadata
            
            results = await asyncio.to_thread(
                self.vectorstore.similarity_search_with_score,
                query,
                **search_kwargs
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in similarity search with scores: {e}")
            return []
    
    async def get_related_documents(
        self, 
        paper_id: str, 
        k: int = 5
    ) -> List[Document]:
        """Get documents related to a specific paper"""
        try:
            # Search for documents from the same paper
            same_paper_docs = await self.similarity_search(
                query="",  # Empty query to get by filter
                k=k*2,  # Get more to filter
                filter_metadata={"paper_id": paper_id}
            )
            
            if same_paper_docs:
                # If we have content from the same paper, find similar content from other papers
                sample_content = same_paper_docs[0].page_content
                
                related_docs = await self.similarity_search(
                    query=sample_content[:500],  # Use first 500 chars as query
                    k=k,
                    filter_metadata={"paper_id": {"$ne": paper_id}}  # Exclude same paper
                )
                
                return related_docs
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting related documents: {e}")
            return []
    
    async def get_document_statistics(self) -> Dict[str, Any]:
        """Get statistics about the vector store"""
        try:
            # Get collection info
            collection_info = self.collection.count()
            
            # Query some sample documents to analyze metadata
            sample_docs = await self.similarity_search("", k=100)  # Get sample
            
            # Analyze papers
            paper_ids = set()
            venues = {}
            authors = set()
            extraction_methods = {}
            
            for doc in sample_docs:
                metadata = doc.metadata
                
                if metadata.get("paper_id"):
                    paper_ids.add(metadata["paper_id"])
                
                if metadata.get("venue"):
                    venue = metadata["venue"]
                    venues[venue] = venues.get(venue, 0) + 1
                
                if metadata.get("authors"):
                    if isinstance(metadata["authors"], list):
                        authors.update(metadata["authors"])
                
                if metadata.get("extraction_method"):
                    method = metadata["extraction_method"]
                    extraction_methods[method] = extraction_methods.get(method, 0) + 1
            
            return {
                "total_documents": collection_info,
                "unique_papers": len(paper_ids),
                "top_venues": sorted(venues.items(), key=lambda x: x[1], reverse=True)[:10],
                "unique_authors": len(authors),
                "extraction_methods": extraction_methods,
                "sample_size": len(sample_docs)
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {"error": str(e)}
    
    async def build_citation_graph(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a citation network graph from papers"""
        try:
            # Create nodes and edges for citation network
            nodes = []
            edges = []
            paper_lookup = {}
            
            # Create nodes from papers
            for paper in papers:
                paper_id = paper.get("url", str(uuid.uuid4()))
                paper_lookup[paper.get("title", "")] = paper_id
                
                node = {
                    "id": paper_id,
                    "title": paper.get("title", "Unknown"),
                    "authors": paper.get("authors", [])[:3],  # First 3 authors
                    "citations": paper.get("citations", 0),
                    "venue": paper.get("venue", "Unknown"),
                    "year": self.extract_year(paper.get("publication_date")),
                    "size": min(paper.get("citations", 0) / 10, 50) + 10  # Node size based on citations
                }
                nodes.append(node)
            
            # Try to identify citation relationships
            # This is simplified - in practice, you'd need better citation parsing
            for paper in papers:
                if paper.get("references"):
                    source_id = paper.get("url", "")
                    
                    for ref in paper.get("references", [])[:10]:  # Limit to first 10 references
                        # Try to match reference to existing papers
                        for other_paper in papers:
                            if other_paper.get("title") and other_paper.get("title") in ref:
                                target_id = other_paper.get("url", "")
                                if source_id != target_id:
                                    edges.append({
                                        "source": source_id,
                                        "target": target_id,
                                        "type": "citation"
                                    })
                                break
            
            return {
                "nodes": nodes,
                "edges": edges,
                "statistics": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "density": len(edges) / (len(nodes) * (len(nodes) - 1)) if len(nodes) > 1 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error building citation graph: {e}")
            return {"nodes": [], "edges": [], "statistics": {}}
    
    async def find_research_clusters(self, query: str, k: int = 20) -> Dict[str, Any]:
        """Find clusters of related research"""
        try:
            # Get relevant documents
            docs_with_scores = await self.similarity_search_with_scores(query, k=k)
            
            if not docs_with_scores:
                return {"clusters": [], "papers": []}
            
            # Group documents by paper
            paper_groups = {}
            for doc, score in docs_with_scores:
                paper_id = doc.metadata.get("paper_id", "unknown")
                if paper_id not in paper_groups:
                    paper_groups[paper_id] = {
                        "paper_id": paper_id,
                        "title": doc.metadata.get("title", "Unknown"),
                        "documents": [],
                        "avg_score": 0,
                        "venue": doc.metadata.get("venue", "Unknown")
                    }
                
                paper_groups[paper_id]["documents"].append((doc, score))
            
            # Calculate average scores and sort
            clustered_papers = []
            for paper_data in paper_groups.values():
                scores = [score for _, score in paper_data["documents"]]
                paper_data["avg_score"] = sum(scores) / len(scores)
                paper_data["document_count"] = len(paper_data["documents"])
                clustered_papers.append(paper_data)
            
            # Sort by relevance score
            clustered_papers.sort(key=lambda x: x["avg_score"], reverse=True)
            
            # Group by venue/topic for clustering
            venue_clusters = {}
            for paper in clustered_papers:
                venue = paper["venue"]
                if venue not in venue_clusters:
                    venue_clusters[venue] = []
                venue_clusters[venue].append(paper)
            
            clusters = [
                {
                    "cluster_id": venue,
                    "papers": papers,
                    "size": len(papers),
                    "avg_relevance": sum(p["avg_score"] for p in papers) / len(papers)
                }
                for venue, papers in venue_clusters.items()
            ]
            
            clusters.sort(key=lambda x: x["avg_relevance"], reverse=True)
            
            return {
                "clusters": clusters,
                "total_papers": len(clustered_papers),
                "query": query
            }
            
        except Exception as e:
            logger.error(f"Error finding research clusters: {e}")
            return {"clusters": [], "papers": []}
    
    def clean_content(self, content: str) -> str:
        """Clean and normalize content for vector storage"""
        # Remove excessive whitespace
        content = " ".join(content.split())
        
        # Remove very short lines that might be artifacts
        lines = content.split('\n')
        cleaned_lines = [line.strip() for line in lines if len(line.strip()) > 10]
        
        return '\n'.join(cleaned_lines)
    
    def extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        
        try:
            if isinstance(date_str, str):
                # Try different date formats
                for fmt in ["%Y-%m-%d", "%Y", "%Y-%m"]:
                    try:
                        return datetime.strptime(date_str[:len(fmt)], fmt).year
                    except ValueError:
                        continue
            return None
        except:
            return None
    
    async def close(self):
        """Close the vector store connection"""
        try:
            # ChromaDB doesn't need explicit closing, but we can clear references
            self.vectorstore = None
            self.chroma_client = None
            self.collection = None
            logger.info("Vector store closed successfully")
        except Exception as e:
            logger.error(f"Error closing vector store: {e}")