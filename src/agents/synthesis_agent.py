from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import logging
from datetime import datetime, timezone
import re

logger = logging.getLogger(__name__)

class KeyFinding(BaseModel):
    """Structure for a key research finding"""
    finding: str = Field(description="The main finding or insight")
    evidence: List[str] = Field(description="Supporting evidence from papers")
    confidence: float = Field(description="Confidence level (0-1)")
    papers: List[str] = Field(description="Paper titles that support this finding")

class ResearchGap(BaseModel):
    """Structure for identified research gaps"""
    gap: str = Field(description="Description of the research gap")
    significance: str = Field(description="Why this gap is important")
    suggested_direction: str = Field(description="Suggested research direction")

class SynthesisResult(BaseModel):
    """Complete synthesis result structure"""
    summary: str = Field(description="Executive summary of the research area")
    key_findings: List[KeyFinding] = Field(description="Key findings from the literature")
    research_gaps: List[ResearchGap] = Field(description="Identified research gaps")
    methodology_trends: List[str] = Field(description="Common methodological approaches")
    future_directions: List[str] = Field(description="Suggested future research directions")
    citation_network: Dict[str, Any] = Field(description="Important citation relationships")
    timeline_insights: List[Dict[str, str]] = Field(description="Temporal trends in research")

class SynthesisAgent:
    """Agent responsible for synthesizing research findings"""
    
    def __init__(self, config):
        self.config = config
        self.llm = ChatGoogleGenerativeAI(
            temperature=0.3,
            model="gemini-1.5-flash",
            api_key=config.google_api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=SynthesisResult)
    
    def normalize_datetime(self, dt_input) -> Optional[datetime]:
        """Normalize datetime to UTC timezone-aware datetime"""
        if not dt_input:
            return None
            
        try:
            if isinstance(dt_input, str):
                # Handle ISO format strings
                if dt_input.endswith('Z'):
                    dt_input = dt_input[:-1] + '+00:00'
                
                # Parse the datetime
                dt = datetime.fromisoformat(dt_input)
            else:
                dt = dt_input
            
            # Convert to timezone-aware if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC if it has a different timezone
                dt = dt.astimezone(timezone.utc)
                
            return dt
            
        except Exception as e:
            logger.warning(f"Could not parse datetime: {dt_input}, error: {e}")
            return None
    
    async def synthesize_research(
        self,
        query: str,
        papers: List[Dict],
        is_web_extracted: bool = False,
    ) -> Dict[str, Any]:
        """Main synthesis function"""
        try:
            # Prepare data for synthesis
            synthesis_data = self.prepare_synthesis_data(papers)
                
            # Generate different aspects of synthesis
            summary = await self.generate_summary(query, synthesis_data)
            key_findings = await self.extract_key_findings(query, synthesis_data)
            research_gaps = await self.identify_research_gaps(query, synthesis_data)
            methodology_trends = await self.analyze_methodology_trends(synthesis_data)
            future_directions = await self.suggest_future_directions(query, synthesis_data)
            citation_network = self.analyze_citation_network(synthesis_data["unique_papers"])
            timeline_insights = self.analyze_temporal_trends(synthesis_data["unique_papers"])
            
            # Combine all results
            result = {
                "summary": summary,
                "key_findings": key_findings,
                "research_gaps": research_gaps,
                "methodology_trends": methodology_trends,
                "future_directions": future_directions,
                "citation_network": citation_network,
                "timeline_insights": timeline_insights,
                "meta_analysis": {
                    "local_papers": 0 if is_web_extracted else synthesis_data.get("total_papers"),
                    "web_extracted_content": 0 if not is_web_extracted else synthesis_data.get("total_papers"),
                    "avg_citations": sum(p.get("citations", 0) for p in papers) / max(len(papers), 1),
                    "date_range": self.get_date_range(papers),
                    "top_venues": self.get_top_venues(papers)
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            return {
                "summary": f"Error during synthesis: {e}",
                "key_findings": [],
                "research_gaps": [],
                "methodology_trends": [],
                "future_directions": [],
                "citation_network": {},
                "timeline_insights": [],
                "meta_analysis": {}
            }
    
    def prepare_synthesis_data(self, papers: List[Dict]) -> Dict[str, Any]:
        """Prepare and structure data for synthesis"""
        
        # Create paper-content mapping
        content_by_paper = {}
        seen_urls = set()
        unique_papers = []
        for content in papers:
            paper_id = content.get("url", "")
            content_by_paper[paper_id] = content
        
        # Combine paper metadata with content
        enriched_papers = []
        for paper in papers:
            paper_data = paper.copy()
            paper_id = paper.get("url", "")

            if paper_id and paper_id not in seen_urls:
                seen_urls.add(paper_id)
                unique_papers.append(paper)
            elif not paper_id:
                unique_papers.append(paper)
            
            if paper_id in content_by_paper:
                content = content_by_paper[paper_id]
                paper_data["full_text"] = content.get("text", "")
                paper_data["sections"] = content.get("sections", [])
                paper_data["references"] = content.get("references", [])
                paper_data["has_content"] = True
            else:
                paper_data["has_content"] = False
            
            enriched_papers.append(paper_data)

        
        return {
            "enriched_papers": enriched_papers,
            "unique_papers": unique_papers,
            "total_papers": len(unique_papers),
            "abstracts": [p.get("abstract", "") for p in papers if p.get("abstract")],
            "all_text": " ".join([p.get("text", "") for p in papers])
        }
    
    async def generate_summary(self, query: str, data: Dict[str, Any]) -> str:
        """Generate executive summary"""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a research analyst tasked with creating an executive summary 
            of academic literature. Create a comprehensive but concise summary that captures the main themes, 
            key developments, and current state of research in the given area."""),
            
            HumanMessage(content=f"""
            Research Query: {query}
            
            Papers analyzed: {data['total_papers']}
            
            Key abstracts and content snippets:
            {' '.join(data['abstracts'][:5])}
            
            Please provide a 300-500 word executive summary covering:
            1. The current state of research in this area
            2. Main themes and approaches
            3. Level of research activity and maturity
            4. Key challenges being addressed
            
            Focus on being informative and objective.
            """)
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            return response.content.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Summary generation failed: {e}"
        
    async def generate_cluster_label(self, abstracts, titles):
        """Generate a concise, meaningful label for a cluster using AI"""
        # Sample abstracts and titles for labeling
        sample_abstracts = abstracts[:3]
        sample_titles = titles[:10]
        
        # Create prompt text
        titles_text = "\n".join([f"- {title}" for title in sample_titles])
        abstracts_text = "\n\n".join([f"Abstract {i+1}: {abs_text[:300]}..." 
                                    for i, abs_text in enumerate(sample_abstracts)])
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a research analyst tasked with creating concise topic labels 
            for academic research clusters. Generate precise, academic terminology that captures the core 
            research area in 2-4 words maximum."""),
            
            HumanMessage(content=f"""
            Based on these research paper titles and abstracts, generate a concise research topic label:

            TITLES:
            {titles_text}

            ABSTRACTS:
            {abstracts_text}

            Requirements:
            - 1-3 words maximum
            - No explanation your response must be solely the generated label
            - Descriptive and specific
            - Academic/technical terminology
            - Captures the core research area
    

            Topic Label:""")
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            return response.content.strip()
        except Exception as e:
            logger.error(f"Error generating cluster label: {e}")
            return f"Research Cluster {hash(str(abstracts[:100])) % 1000}"
                    
    async def extract_key_findings(
        self, 
        query: str, 
        data: Dict[str, Any], 
    ) -> List[Dict[str, Any]]:
        """Extract key findings from the literature"""
                
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a research analyst extracting key findings from academic literature. 
            Identify the most significant and well-supported findings, avoiding speculation and focusing on 
            concrete results and conclusions."""),
            
            HumanMessage(content=f"""
            Research Query: {query}
            
            Relevant content from papers:
            {' '.join(data['abstracts'][:5])}
            
            Extract 5-8 key findings. For each finding, provide:
            1. The main finding (clear and specific)
            2. Level of evidence/support (strong, moderate, limited)
            3. Which aspects support this finding
            
            Format as JSON array with objects containing: finding, evidence_level, supporting_points
            """)
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            
            
            # Parse JSON response
            try:
                content = response.content.strip()
                content = re.sub(r'```(?:json)?\s*', '', content)
                content = content.replace('```', '').strip()
                findings_json = json.loads(content)
                return findings_json
            except json.JSONDecodeError:
                # Fallback parsing if JSON fails
                return self.parse_findings_from_text(response.content)
                
        except Exception as e:
            logger.error(f"Error extracting key findings: {e}")
            return []
    
    async def identify_research_gaps(self, query: str, data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Identify gaps in current research"""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a research strategist identifying gaps and opportunities 
            in academic literature. Focus on methodological gaps, unexplored areas, and limitations 
            mentioned in the current research."""),
            
            HumanMessage(content=f"""
            Research Query: {query}
            
            Analysis of {data['total_papers']} papers in this area.
            
            Sample content: {data['all_text'][:5000]}
            
            Identify 3-5 significant research gaps or opportunities. For each gap:
            1. Description of what's missing or understudied
            2. Why this gap is significant
            3. Potential research direction to address it
            
            Format as JSON array with objects containing: gap, significance, suggested_direction
            """)
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            try:
                content = response.content.strip()
                content = re.sub(r'```(?:json)?\s*', '', content)
                content = content.replace('```', '').strip()
                gaps_json = json.loads(content)
                return gaps_json
            except json.JSONDecodeError:
                return self.parse_gaps_from_text(response.content)
        except Exception as e:
            logger.error(f"Error identifying research gaps: {e}")
            return []
    
    async def analyze_methodology_trends(self, data: Dict[str, Any]) -> List[str]:
        """Analyze common methodological approaches"""
        
        # Extract methodology information from papers with content
        methodologies = []
        for paper in data['enriched_papers']:
            if paper.get('has_content'):
                # Look for methodology sections
                for section in paper.get('sections', []):
                    if any(keyword in section for keyword in ['method', 'approach', 'technique', 'model']):
                        methodologies.append(section[:500])
        
        if not methodologies:
            return ["Insufficient methodology information available"]
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are analyzing methodological trends in academic research. 
            Identify the most common approaches, techniques, and methodological patterns."""),
            
            HumanMessage(content=f"""
            Methodology sections from papers:
            {' '.join(methodologies[:5])}
            
            Identify 5-7 key methodological trends or common approaches.
            Return as a simple list of strings, each describing a methodological trend.
            """)
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            trends = [line.strip('- ').strip() for line in response.content.split('\n') if line.strip()]
            return trends[:7]  # Limit to 7 trends
        except Exception as e:
            logger.error(f"Error analyzing methodology trends: {e}")
            return ["Methodology analysis failed"]
    
    async def suggest_future_directions(self, query: str, data: Dict[str, Any]) -> List[str]:
        """Suggest future research directions"""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a research strategist suggesting future research directions 
            based on current literature analysis. Focus on logical next steps, emerging opportunities, 
            and areas that could benefit from further investigation."""),
            
            HumanMessage(content=f"""
            Research area: {query}
            Literature analysis of {data['total_papers']} papers
            
            Content sample: {data['all_text'][:1500]}
            
            Suggest 5-6 promising future research directions based on:
            1. Current limitations in the field
            2. Emerging trends and opportunities
            3. Technological or methodological advances
            4. Practical applications that need development
            
            Return as a list of specific, actionable research directions.
            """)
        ])
        
        try:
            response = await self.llm.ainvoke(prompt.format_messages())
            directions = [line.strip('- ').strip() for line in response.content.split('\n') if line.strip()]
            return directions[:6]
        except Exception as e:
            logger.error(f"Error suggesting future directions: {e}")
            return ["Future directions analysis failed"]
    
    def analyze_citation_network(self, papers: List[Dict]) -> Dict[str, Any]:
        """Analyze citation patterns and influential papers"""
        
        if not papers:
            return {}
        
        # Sort papers by citations
        sorted_papers = sorted(papers, key=lambda x: x.get('citations', 0), reverse=True)
        
        # Identify highly cited papers
        highly_cited = [
            {
                "title": paper.get('title', 'Unknown'),
                "citations": paper.get('citations', 0),
                "authors": paper.get('authors', [])[:3],
                "venue": paper.get('venue', 'Unknown')
            }
            for paper in sorted_papers[:10] if paper.get('citations', 0) > 0
        ]
        
        # Calculate citation statistics
        citation_counts = [p.get('citations', 0) for p in papers]
        avg_citations = sum(citation_counts) / len(citation_counts) if citation_counts else 0
        
        return {
            "highly_cited_papers": highly_cited,
            "citation_stats": {
                "average_citations": round(avg_citations, 2),
                "max_citations": max(citation_counts) if citation_counts else 0,
                "total_citations": sum(citation_counts),
                "papers_with_citations": len([c for c in citation_counts if c > 0])
            }
        }
    
    def analyze_temporal_trends(self, papers: List[Dict]) -> List[Dict[str, str]]:
        """Analyze temporal trends in research"""
        
        # Group papers by publication year
        year_counts = {}
        valid_dates = []
        
        for paper in papers:
            pub_date = paper.get('publication_date')
            normalized_date = self.normalize_datetime(pub_date)
            
            if normalized_date:
                year = normalized_date.year
                year_counts[year] = year_counts.get(year, 0) + 1
                valid_dates.append(normalized_date)
        
        if not year_counts:
            return [{"trend": "Insufficient temporal data", "description": "Publication dates not available"}]
        
        # Analyze trends
        sorted_years = sorted(year_counts.keys())
        trends = []
        
        if len(sorted_years) >= 3:
            recent_years = sorted_years[-3:]
            early_years = sorted_years[:3] if len(sorted_years) > 3 else sorted_years[:-1]
            
            recent_avg = sum(year_counts[y] for y in recent_years) / len(recent_years)
            early_avg = sum(year_counts[y] for y in early_years) / len(early_years)
            
            if recent_avg > early_avg * 1.5:
                trends.append({
                    "trend": "Increasing Research Activity",
                    "description": f"Research activity has increased significantly in recent years ({recent_years[0]}-{recent_years[-1]})"
                })
            elif recent_avg < early_avg * 0.7:
                trends.append({
                    "trend": "Declining Research Activity", 
                    "description": f"Research activity has declined in recent years"
                })
            else:
                trends.append({
                    "trend": "Stable Research Activity",
                    "description": f"Research activity has remained relatively stable"
                })
        
        # Peak year
        peak_year = max(year_counts.keys(), key=lambda y: year_counts[y])
        trends.append({
            "trend": "Peak Research Year",
            "description": f"{peak_year} had the highest number of publications ({year_counts[peak_year]} papers)"
        })
        
        return trends
    
    def get_date_range(self, papers: List[Dict]) -> Dict[str, str]:
        """Get the date range of papers"""
        valid_dates = []
        
        for paper in papers:
            pub_date = paper.get('publication_date')
            normalized_date = self.normalize_datetime(pub_date)
            if normalized_date:
                valid_dates.append(normalized_date)
        
        if valid_dates:
            min_date = min(valid_dates)
            max_date = max(valid_dates)
            span_days = (max_date - min_date).days
            span_years = span_days / 365.25
            
            return {
                "earliest": min_date.strftime("%Y-%m-%d"),
                "latest": max_date.strftime("%Y-%m-%d"),
                "span_years": round(span_years, 1)
            }
        return {"earliest": "Unknown", "latest": "Unknown", "span_years": 0}
    
    def get_top_venues(self, papers: List[Dict]) -> List[Dict[str, Any]]:
        """Get top publication venues"""
        venue_counts = {}
        for paper in papers:
            venue = paper.get('venue')
            if venue and venue.strip():
                venue_counts[venue] = venue_counts.get(venue, 0) + 1
        
        # Sort by count and return top venues
        sorted_venues = sorted(venue_counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {"venue": venue, "count": count, "percentage": round(count/len(papers)*100, 1)}
            for venue, count in sorted_venues[:10]
        ]
    
    def parse_findings_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse findings from plain text when JSON parsing fails"""
        findings = []
        lines = text.split('\n')
        
        current_finding = {}
        for line in lines:
            line = line.strip()
            if line and not line.startswith('```'):
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '-')):
                    if current_finding:
                        findings.append(current_finding)
                    current_finding = {
                        "finding": line,
                        "evidence_level": "moderate",
                        "supporting_points": []
                    }
                elif current_finding and line:
                    current_finding["supporting_points"].append(line)
        
        if current_finding:
            findings.append(current_finding)
        
        return findings[:8]  # Limit to 8 findings
    
    def parse_gaps_from_text(self, text: str) -> List[Dict[str, str]]:
        """Parse research gaps from plain text when JSON parsing fails"""
        gaps = []
        lines = text.split('\n')
        
        current_gap = {}
        for line in lines:
            line = line.strip()
            if line and not line.startswith('```'):
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '-')):
                    if current_gap:
                        gaps.append(current_gap)
                    current_gap = {
                        "gap": line,
                        "significance": "Identified research opportunity",
                        "suggested_direction": "Further investigation needed"
                    }
        
        if current_gap:
            gaps.append(current_gap)
        
        return gaps[:5]  # Limit to 5 gaps