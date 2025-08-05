import asyncio
import aiohttp
from typing import List, Dict, Optional
import arxiv
from scholarly import scholarly
import requests
from bs4 import BeautifulSoup
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
    pdf_url: Optional[str]
    publication_date: Optional[datetime]
    venue: Optional[str]
    citations: int = 0
    doi: Optional[str] = None
    source: str = "unknown"
    
class DiscoveryAgent:
    """Agent responsible for discovering academic papers"""
    
    def __init__(self, config):
        self.config = config
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_papers(self, query: str, max_results: int = None) -> List[Paper]:
        """Main search function that coordinates all sources"""
        max_results = max_results or self.config.max_papers_per_search
        
        # Search across all sources concurrently
        tasks = [
            self.search_arxiv(query, max_results // 2),
            #self.search_semantic_scholar(query, max_results // 3),
            self.search_google_scholar(query, max_results // 2),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine and deduplicate results
        all_papers = []
        for result in results:
            if isinstance(result, list):
                all_papers.extend(result)
            else:
                logger.error(f"Search error: {result}")
        
        return self.deduplicate_papers(all_papers)[:max_results]
    
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
                    url=result.entry_id,
                    pdf_url=result.pdf_url,
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
                            url=item.get("url", ""),
                            pdf_url=pdf_url,
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
        """Search Google Scholar (using scholarly library)"""
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
                        url=result.get("pub_url", ""),
                        pdf_url=result.get("eprint_url"),
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