import asyncio
import aiohttp
from typing import List, Dict, Optional
import arxiv
from scholarly import scholarly
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@dataclass
class Paper:
    """Paper data structure"""
    title: str
    authors: List[str]
    abstract: str
    url: str
    publication_date: Optional[datetime]
    venue: Optional[str]
    citations: int = 0
    doi: Optional[str] = None
    source: str = "unknown"
    
class DiscoveryAgent:
    """Agent responsible for discovering academic papers"""
    
    def __init__(self, config, vector_store=None):
        self.config = config
        self.session = None
        self.vector_store = vector_store
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def is_paper_in_vectorstore(self, paper: Paper) -> bool:
        """Check if paper already exists in vector store"""
        if not self.vector_store:
            return False
        
        try:
            # Check by URL/paper_id
            if paper.url:
                existing_docs = await self.vector_store.get_same_documents(paper.url, k=1)
                if existing_docs:
                    return True
            
            # Check by DOI if available
            if paper.doi:
                existing_docs = await self.vector_store.similarity_search(
                    query="",
                    k=1,
                    filter_metadata={"doi": paper.doi}
                )
                if existing_docs:
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking paper existence: {e}")
            return False
        

    async def filter_existing_papers(self, papers: List[Paper]) -> List[Paper]:
        """Filter out papers that already exist in vector store"""
        if not self.vector_store:
            return papers
        
        filtered_papers = []
        existing_count = 0
        
        for paper in papers:
            if await self.is_paper_in_vectorstore(paper):
                existing_count += 1
                logger.debug(f"Skipping existing paper: {paper.title[:50]}...")
            else:
                filtered_papers.append(paper)
        
        logger.info(f"Filtered out {existing_count} existing papers, {len(filtered_papers)} new papers remain")
        return filtered_papers
        
    async def search_papers(self, query: str, max_results: int = None) -> List[Paper]:
        """Iterative search approach with exponential backoff"""
        
        if max_results is None:
            max_results = 20
        
        all_papers = []
        search_attempts = 0
        max_attempts = 5
        
        while len(all_papers) < max_results and search_attempts < max_attempts:
            search_attempts += 1
            
            # Calculate how many more we need
            search_count = min( max_results * search_attempts * 2, 75)
            
            logger.info(f"Search attempt {search_attempts}: looking for {search_count} papers")
            
            # Search with current parameters
            await asyncio.sleep(2 * search_attempts)  
            
            tasks = [
                self.search_arxiv(query, search_count // 2),
                #self.search_semantic_scholar(query, max_results // 3),
                self.search_google_scholar(query, search_count // 2),
            ]
            
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                batch_papers = []
                for result in results:
                    if isinstance(result, list):
                        batch_papers.extend(result)
                    else:
                        logger.error(f"Search error in attempt {search_attempts}: {result}")
                
                # Deduplicate and filter
                batch_papers = self.deduplicate_papers(batch_papers)
                filtered_batch = await self.filter_existing_papers(batch_papers)
                
                # Add new papers
                for paper in filtered_batch:
                    if not any(p.url == paper.url for p in all_papers):
                        all_papers.append(paper)
                
                logger.info(f"Attempt {search_attempts}: found {len(filtered_batch)} new papers, total: {len(all_papers)}")
                
            except Exception as e:
                logger.error(f"Search attempt {search_attempts} failed: {e}")
        
        logger.info(f"Search completed: {len(all_papers)} papers found after {search_attempts} attempts")
        return all_papers
    
    async def search_arxiv(self, query: str, max_results: int) -> List[Paper]:
        """Search ArXiv papers"""
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            papers = []
            for result in client.results(search):
                paper = Paper(
                    title=result.title,
                    authors=[author.name for author in result.authors],
                    abstract=result.summary,
                    url=result.pdf_url,
                    publication_date=result.published,
                    venue="arXiv",
                    source="arxiv",
                    doi=result.doi
                )
                papers.append(paper)
                
            return papers
            
        except Exception as e:
            logger.error(f"ArXiv search error: {e}")
            return []
    
    async def search_semantic_scholar(self, query: str, max_results: int) -> List[Paper]:
        """Search Semantic Scholar"""
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            headers = {}
            if self.config.semantic_scholar_key:
                print("true")
                headers["x-api-key"] = self.config.semantic_scholar_key
            
            params = {
                "query": query,
                "limit": max_results,
                "fields": "title,authors,abstract,url,venue,year,citationCount,externalIds"
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    papers = []
                    
                    for item in data.get("data", []):
                        # Parse publication date
                        pub_date = None
                        if item.get("year"):
                            pub_date = datetime(item["year"], 1, 1)
                        
                        # Extract PDF URL from external IDs
                        pdf_url = None
                        external_ids = item.get("externalIds", {})
                        if "ArXiv" in external_ids:
                            pdf_url = f"https://arxiv.org/pdf/{external_ids['ArXiv']}.pdf"
                        
                        paper = Paper(
                            title=item.get("title", ""),
                            authors=[author.get("name", "") for author in item.get("authors", [])],
                            abstract=item.get("abstract", ""),
                            url=pdf_url,
                            publication_date=pub_date,
                            venue=item.get("venue"),
                            citations=item.get("citationCount", 0),
                            doi=external_ids.get("DOI"),
                            source="semantic_scholar"
                        )
                        papers.append(paper)
                    
                    return papers
                else:
                    logger.error(f"Semantic Scholar API error: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Semantic Scholar search error: {e}")
            return []
    
    async def search_google_scholar(self, query: str, max_results: int) -> List[Paper]:
        """Search Google Scholar"""
        try:
            papers = []
            search_query = scholarly.search_pubs(query)
            
            count = 0
            while count < max_results:
                try:
                    result = next(search_query)
                    
                    # Parse publication date
                    pub_date = None
                    bib = result.get("bib", {})

                    if "pub_year" in bib:
                        try:
                            pub_date = datetime(int(bib["pub_year"]), 1, 1)
                        except (ValueError, TypeError):
                            pub_date = None

                    paper = Paper(
                        title=bib.get("title", ""),
                        authors=bib.get("author", ""),
                        abstract=bib.get("abstract", ""),
                        url=result.get("eprint_url", ""),
                        publication_date=pub_date,
                        venue=bib.get("venue"),
                        citations=result.get("num_citations", 0),
                        source="google_scholar"
                    )
                    papers.append(paper)
                    count += 1
                    
                    # Rate limiting
                    await asyncio.sleep(self.config.request_delay)
                    
                except StopIteration:
                    break
                except Exception as e:
                    logger.warning(f"Error processing Google Scholar result: {e}")
                    continue
            
            return papers
            
        except Exception as e:
            logger.error(f"Google Scholar search error: {e}")
            return []
    
    def deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """Remove duplicate papers based on title similarity"""
        if not papers:
            return []
        
        unique_papers = []
        seen_titles = set()
        
        for paper in papers:
            # Normalize title for comparison
            normalized_title = paper.title.lower().strip()
            normalized_title = ''.join(c for c in normalized_title if c.isalnum() or c.isspace())
            
            if normalized_title not in seen_titles and len(normalized_title) > 10:
                seen_titles.add(normalized_title)
                unique_papers.append(paper)
        
        # Sort by citation count and recency
        unique_papers.sort(
            key=lambda p: (
                p.citations if p.citations else 0,
                p.publication_date if p.publication_date else datetime.min
            ),
            reverse=True
        )
        
        return unique_papers