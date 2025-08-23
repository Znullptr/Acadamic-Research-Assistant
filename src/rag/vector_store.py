from typing import List, Dict, Any, Optional, Tuple
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from src.agents.synthesis_agent import SynthesisAgent
import chromadb
from chromadb.config import Settings
import asyncio
import re 
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
            
            return results
            
        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            return []
    
    async def similarity_search_with_scores(
        self, 
        query: str, 
        k: int = 5,
    ) -> List[Tuple[Document, float]]:
        """Perform similarity search with relevance scores"""
        try:
            search_kwargs = {"k": k}
            filter = None
            #query_words = set(re.findall(r'\b\w+\b', query.lower()))
            '''
            # Remove common stop words
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            query_words = query_words - stop_words
            filter = {
                "$or": [
                    {"abstract": {"$in": [word]}} for word in query_words
                ]
            }
            '''

            if filter:
                search_kwargs["filter"] = filter
            
            results = await asyncio.to_thread(
                self.vectorstore.similarity_search_with_score,
                query,
                **search_kwargs
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in similarity search with scores: {e}")
            return []
    
    async def get_same_documents(
        self, 
        paper_id: str, 
        k: int = 5
    ) -> List[Document]:
        """Get documents related to a specific paper"""
        try:
            # Search for documents from the same paper
            same_paper_docs = await self.similarity_search(
                query="", 
                k=k*2,
                filter_metadata={"paper_id": paper_id}
            )
            if same_paper_docs:
                return same_paper_docs
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
            sample_docs = await self.similarity_search("", k=10000) 
            
            # Analyze papers
            paper_ids = set()
            venues = {}
            authors = set()
            
            for doc in sample_docs:
                metadata = doc.metadata
                
                if metadata.get("paper_id"):
                    paper_ids.add(metadata["paper_id"])
                
                if metadata.get("venue"):
                    venue = metadata["venue"]
                    venues[venue] = venues.get(venue, 0) + 1
                
                if metadata.get("authors"):
                        authors.update(metadata["authors"].split(','))
            
            return {
                "total_documents": collection_info,
                "unique_papers": len(paper_ids),
                "top_venue": sorted(venues.items(), key=lambda x: x[1], reverse=True)[0][0],
                "unique_authors": len(authors),
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
            
            for paper in papers:
                if paper.get("references"):
                    source_id = paper.get("url", "")
                    
                    for ref in paper.get("references", [])[:10]: 
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
        
    async def find_research_trends(self, synthesis_agent: SynthesisAgent, n_clusters: int = 5, min_papers_per_cluster: int = 3) -> Dict[str, Any]:
        """Find research trends using content-based clustering with AI-generated labels
        
        Args:
            n_clusters: Number of clusters to create
            min_papers_per_cluster: Minimum papers required for a cluster to be included
        """
        try:
            from sklearn.cluster import KMeans
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Get ALL documents from vectorstore
            docs = await self.similarity_search("", k=1000)
            
            if not docs:
                return []
            
            # Group by paper id
            paper_data = {}
            paper_contents = []
            paper_ids_ordered = []
            
            for doc in docs:

                paper_id = doc.metadata.get("paper_id", "unknown")
                if paper_id not in paper_data:
                    
                    # Extract abstract 
                    abstract = doc.page_content
                    
                    paper_data[paper_id] = {
                        "paper_id": paper_id,
                        "title": doc.metadata.get("title", ""),
                        "abstract": abstract,
                    }
                    
                    paper_contents.append(abstract)
                    paper_ids_ordered.append(paper_id)
        
            
            if len(paper_contents) < n_clusters:
                n_clusters = max(2, len(paper_contents) // 2)
            
            # Vectorize abstracts using TF-IDF
            vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.95
            )
            
            tfidf_matrix = vectorizer.fit_transform(paper_contents)
            
            # Perform K-means clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(tfidf_matrix)
            
            # Group papers by cluster
            clusters = {}
            for idx, cluster_id in enumerate(cluster_labels):
                paper_id = paper_ids_ordered[idx]
                
                if cluster_id not in clusters:
                    clusters[cluster_id] = {
                        "papers": [],
                        "abstracts": []
                    }
                
                paper = paper_data[paper_id]
                clusters[cluster_id]["papers"].append(paper)
                clusters[cluster_id]["abstracts"].append(paper["abstract"])
                
            # Filter clusters by minimum paper count
            filtered_clusters = {k: v for k, v in clusters.items() 
                            if len(v["papers"]) >= min_papers_per_cluster}
            
            # Generate labels for each cluster
            labeled_trends = []
            for cluster_id, cluster_data in filtered_clusters.items():
                papers = cluster_data["papers"]
                unique_papers = len(papers)
                
                # Generate AI label for this cluster
                cluster_label = await synthesis_agent.generate_cluster_label(
                    cluster_data["abstracts"], 
                    [p["title"] for p in papers]
                )   
                
                trend = {
                    "topic": cluster_label,
                    "cluster_id": cluster_id,
                    "unique_papers": unique_papers,
                }
                
                labeled_trends.append(trend)
            
            # Sort by number of papers
            labeled_trends.sort(key=lambda x: x["unique_papers"], reverse=True)
            
            trends = [
                {
                    "label": trend["topic"],
                    "size": trend["unique_papers"]
                } 
                for trend in labeled_trends
            ]
            
            return trends
            
        except Exception as e:
            logger.error(f"Error finding research trends: {e}")
            return []
    
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