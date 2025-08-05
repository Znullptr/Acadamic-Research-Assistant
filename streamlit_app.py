import streamlit as st
import requests
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Configure Streamlit page
st.set_page_config(
    page_title="Academic Research Assistant",
    page_icon="🔬",
    layout="wide"
)

# API base URL
API_BASE_URL = "http://localhost:8000"

def main():
    st.title("🔬 Academic Research Assistant")
    st.markdown("AI-powered research discovery and synthesis using LangChain, LangGraph, and advanced PDF processing")
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page",
        ["Research", "Knowledge Base", "Statistics", "About"]
    )
    
    if page == "Research":
        research_page()
    elif page == "Knowledge Base":
        knowledge_base_page()
    elif page == "Statistics":
        statistics_page()
    elif page == "About":
        about_page()

def research_page():
    st.header("🔍 Research Discovery & Synthesis")
    
    # Research form
    with st.form("research_form"):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            query = st.text_input(
                "Research Query",
                placeholder="e.g., transformer architecture in natural language processing",
                help="Enter your research topic or question"
            )
        
        with col2:
            max_papers = st.number_input(
                "Max Papers",
                min_value=10,
                max_value=100,
                value=50,
                help="Maximum number of papers to analyze"
            )
        
        include_analysis = st.checkbox("Include Deep Analysis", value=True)
        
        submitted = st.form_submit_button("🚀 Start Research")
    
    if submitted and query:
        # Start research task
        with st.spinner("Initiating research task..."):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/research",
                    json={
                        "query": query,
                        "max_papers": max_papers,
                        "include_analysis": include_analysis
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    request_id = data["request_id"]
                    
                    st.success(f"Research task started! Request ID: {request_id}")
                    
                    # Store request ID in session state
                    st.session_state.current_request_id = request_id
                    st.session_state.research_query = query
                    
                    # Monitor progress
                    monitor_research_progress(request_id)
                    
                else:
                    st.error(f"Failed to start research: {response.text}")
                    
            except Exception as e:
                st.error(f"Error: {e}")
    
    # Display results if we have a completed request
    if hasattr(st.session_state, 'current_request_id'):
        display_research_results(st.session_state.current_request_id)

def monitor_research_progress(request_id):
    """Monitor and display research progress"""
    
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    max_wait_time = 300  # 5 minutes
    check_interval = 5   # 5 seconds
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        try:
            response = requests.get(f"{API_BASE_URL}/research/{request_id}/status")
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data["status"]
                progress = status_data.get("progress", "unknown")
                
                # Update progress display
                if current_status == "running":
                    progress_placeholder.info(f"🔄 Status: {progress}")
                    progress_bar = status_placeholder.progress(0)
                    
                    # Estimate progress based on step
                    progress_map = {
                        "discovering papers": 0.2,
                        "extracting content": 0.5,
                        "updating knowledge graph": 0.7,
                        "synthesizing results": 0.9,
                        "quality check": 0.95
                    }
                    
                    progress_value = progress_map.get(progress, 0.1)
                    progress_bar.progress(progress_value)
                    
                elif current_status == "completed":
                    progress_placeholder.success("✅ Research completed!")
                    status_placeholder.empty()
                    break
                    
                elif current_status == "failed":
                    error_msg = status_data.get("error", "Unknown error")
                    progress_placeholder.error(f"❌ Research failed: {error_msg}")
                    status_placeholder.empty()
                    break
            
            time.sleep(check_interval)
            elapsed_time += check_interval
            
        except Exception as e:
            st.error(f"Error checking status: {e}")
            break
    
    if elapsed_time >= max_wait_time:
        progress_placeholder.warning("⏰ Research is taking longer than expected. Check back later.")

def display_research_results(request_id):
    """Display research results"""
    
    try:
        response = requests.get(f"{API_BASE_URL}/research/{request_id}/results")
        
        if response.status_code == 200:
            results = response.json()
            
            st.header("📊 Research Results")
            
            # Overview metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Papers Found", results["papers_found"])
            with col2:
                st.metric("Content Extracted", results["content_extracted"])
            with col3:
                st.metric("Quality Score", f"{results['quality_score']}/100")
            with col4:
                status_color = "🟢" if results["status"] == "completed" else "🟡"
                st.metric("Status", f"{status_color} {results['status']}")
            
            # Display synthesis results
            if results.get("synthesis"):
                synthesis = results["synthesis"]
                
                # Executive Summary
                if synthesis.get("summary"):
                    st.subheader("📋 Executive Summary")
                    st.write(synthesis["summary"])
                
                # Key Findings
                if synthesis.get("key_findings"):
                    st.subheader("🔍 Key Findings")
                    for i, finding in enumerate(synthesis["key_findings"][:8], 1):
                        with st.expander(f"Finding {i}: {finding.get('finding', 'N/A')[:100]}..."):
                            st.write(f"**Finding:** {finding.get('finding', 'N/A')}")
                            st.write(f"**Evidence Level:** {finding.get('evidence_level', 'N/A')}")
                            if finding.get('supporting_points'):
                                st.write("**Supporting Points:**")
                                for point in finding['supporting_points'][:3]:
                                    st.write(f"• {point}")
                
                # Research Gaps
                if synthesis.get("research_gaps"):
                    st.subheader("🔬 Research Gaps & Opportunities")
                    for gap in synthesis["research_gaps"][:5]:
                        st.write(f"**Gap:** {gap.get('gap', 'N/A')}")
                        st.write(f"**Significance:** {gap.get('significance', 'N/A')}")
                        st.write(f"**Suggested Direction:** {gap.get('suggested_direction', 'N/A')}")
                        st.divider()
                
                # Methodology Trends
                if synthesis.get("methodology_trends"):
                    st.subheader("⚙️ Methodology Trends")
                    for trend in synthesis["methodology_trends"]:
                        st.write(f"• {trend}")
                
                # Future Directions
                if synthesis.get("future_directions"):
                    st.subheader("🚀 Future Research Directions")
                    for direction in synthesis["future_directions"]:
                        st.write(f"• {direction}")
                
                # Citation Network Visualization
                if synthesis.get("citation_network"):
                    st.subheader("📈 Citation Analysis")
                    citation_data = synthesis["citation_network"]
                    
                    if citation_data.get("highly_cited_papers"):
                        # Create citation chart
                        papers_df = pd.DataFrame(citation_data["highly_cited_papers"])
                        
                        if not papers_df.empty:
                            fig = px.bar(
                                papers_df.head(10),
                                x="citations",
                                y="title",
                                orientation="h",
                                title="Top Cited Papers",
                                labels={"citations": "Citation Count", "title": "Paper Title"}
                            )
                            fig.update_layout(height=400)
                            st.plotly_chart(fig, use_container_width=True)
                    
                    # Citation statistics
                    if citation_data.get("citation_stats"):
                        stats = citation_data["citation_stats"]
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Average Citations", round(stats.get("average_citations", 0), 1))
                        with col2:
                            st.metric("Max Citations", stats.get("max_citations", 0))
                        with col3:
                            st.metric("Total Citations", stats.get("total_citations", 0))
                
                # Timeline Analysis
                if synthesis.get("timeline_insights"):
                    st.subheader("📅 Temporal Trends")
                    for insight in synthesis["timeline_insights"]:
                        st.write(f"**{insight.get('trend', 'N/A')}:** {insight.get('description', 'N/A')}")
            
            # Error display
            if results.get("errors"):
                st.subheader("⚠️ Errors Encountered")
                for error in results["errors"]:
                    st.warning(error)
        
        elif response.status_code == 400:
            st.info("Research task is still in progress. Please wait...")
        else:
            st.error(f"Failed to get results: {response.text}")
            
    except Exception as e:
        st.error(f"Error displaying results: {e}")

def knowledge_base_page():
    st.header("💾 Knowledge Base Search")
    
    # Search interface
    search_query = st.text_input(
        "Search Query",
        placeholder="Enter keywords to search the knowledge base",
        help="Search through processed research papers"
    )
    
    col1, col2 = st.columns([1, 1])
    with col1:
        num_results = st.slider("Number of Results", 5, 50, 10)
    
    if st.button("🔍 Search") and search_query:
        with st.spinner("Searching knowledge base..."):
            try:
                response = requests.get(
                    f"{API_BASE_URL}/search",
                    params={"query": search_query, "k": num_results}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data["results"]
                    
                    st.success(f"Found {len(results)} results for: '{search_query}'")
                    
                    for i, result in enumerate(results, 1):
                        with st.expander(f"Result {i}: {result['metadata'].get('title', 'Unknown Title')}"):
                            st.write("**Content:**")
                            st.write(result["content"])
                            
                            st.write("**Metadata:**")
                            metadata = result["metadata"]
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Paper ID:** {metadata.get('paper_id', 'N/A')}")
                                st.write(f"**Venue:** {metadata.get('venue', 'N/A')}")
                            with col2:
                                st.write(f"**Type:** {metadata.get('type', 'N/A')}")
                                st.write(f"**Section:** {metadata.get('section_title', 'N/A')}")
                
                else:
                    st.error("Search failed")
                    
            except Exception as e:
                st.error(f"Search error: {e}")
    
    # Research clusters
    st.subheader("🔗 Research Clusters")
    
    cluster_query = st.text_input(
        "Cluster Analysis Query",
        placeholder="Enter a topic to find research clusters"
    )
    
    if st.button("📊 Analyze Clusters") and cluster_query:
        with st.spinner("Analyzing research clusters..."):
            try:
                response = requests.get(
                    f"{API_BASE_URL}/clusters",
                    params={"query": cluster_query, "k": 30}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    clusters = data["clusters"]
                    
                    if clusters:
                        st.success(f"Found {len(clusters)} research clusters")
                        
                        for i, cluster in enumerate(clusters[:5], 1):
                            with st.expander(f"Cluster {i}: {cluster['cluster_id']} ({cluster['size']} papers)"):
                                st.write(f"**Average Relevance:** {cluster['avg_relevance']:.3f}")
                                st.write(f"**Papers in cluster:**")
                                
                                for paper in cluster['papers'][:5]:  # Show top 5 papers
                                    st.write(f"• {paper['title']} (Score: {paper['avg_score']:.3f})")
                    else:
                        st.info("No clusters found for this query")
                
            except Exception as e:
                st.error(f"Cluster analysis error: {e}")

def statistics_page():
    st.header("📊 Knowledge Base Statistics")
    
    if st.button("📈 Refresh Statistics"):
        with st.spinner("Loading statistics..."):
            try:
                response = requests.get(f"{API_BASE_URL}/statistics")
                
                if response.status_code == 200:
                    stats = response.json()
                    
                    # Overview metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Documents", stats.get("total_documents", 0))
                    with col2:
                        st.metric("Unique Papers", stats.get("unique_papers", 0))
                    with col3:
                        st.metric("Unique Authors", stats.get("unique_authors", 0))
                    with col4:
                        st.metric("Sample Size", stats.get("sample_size", 0))
                    
                    # Top venues chart
                    if stats.get("top_venues"):
                        st.subheader("📚 Top Publication Venues")
                        venues_df = pd.DataFrame(stats["top_venues"], columns=["Venue", "Count"])
                        
                        fig = px.bar(
                            venues_df.head(10),
                            x="Count",
                            y="Venue",
                            orientation="h",
                            title="Papers by Venue"
                        )
                        fig.update_layout(height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Extraction methods
                    if stats.get("extraction_methods"):
                        st.subheader("⚙️ Content Extraction Methods")
                        methods = stats["extraction_methods"]
                        
                        methods_df = pd.DataFrame(
                            list(methods.items()),
                            columns=["Method", "Count"]
                        )
                        
                        fig = px.pie(
                            methods_df,
                            values="Count",
                            names="Method",
                            title="Distribution of Extraction Methods"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                
                else:
                    st.error("Failed to load statistics")
                    
            except Exception as e:
                st.error(f"Statistics error: {e}")

def about_page():
    st.header("ℹ️ About Academic Research Assistant")
    
    st.markdown("""
    ## Overview
    
    The Academic Research Assistant is an AI-powered system that helps researchers discover, process, and synthesize academic literature using cutting-edge technologies:
    
    ### 🛠️ Technology Stack
    
    - **LangChain**: Framework for building LLM applications
    - **LangGraph**: Multi-agent workflow orchestration
    - **OpenAI GPT-4**: Large language model for synthesis and analysis
    - **ChromaDB**: Vector database for semantic search
    - **OCR Processing**: Tesseract + pdf2image for scanned document processing
    - **Web Scraping**: Beautiful Soup + Selenium for paper discovery
    - **FastAPI**: High-performance API backend
    - **Streamlit**: Interactive web interface
    
    ### 🔄 Workflow Architecture
    
    1. **Discovery Agent**: Searches ArXiv, Google Scholar, and journal databases
    2. **Extraction Agent**: Processes PDFs with OCR for scanned documents
    3. **Synthesis Agent**: Analyzes content and generates insights
    4. **Knowledge Graph**: Maintains relationships between papers and concepts
    
    ### ✨ Key Features
    
    - **Multi-source Search**: Comprehensive paper discovery across platforms
    - **Intelligent OCR**: Handles both text-based and scanned PDFs
    - **Semantic Analysis**: Vector-based similarity search and clustering
    - **Research Synthesis**: AI-generated summaries and gap analysis
    - **Citation Network**: Analysis of paper relationships and influence
    - **Temporal Trends**: Understanding research evolution over time
    
    ### 🎯 Use Cases
    
    - Literature reviews for research papers
    - Market research and competitive analysis
    - Grant proposal background research
    - Interdisciplinary research discovery
    - Trend analysis and future direction identification
    
    ### 🚀 Getting Started
    
    1. Go to the **Research** page
    2. Enter your research query
    3. Wait for the AI agents to process the literature
    4. Explore the comprehensive synthesis results
    
    ---
    
    **Note**: This is a demonstration system. For production use, ensure proper API keys are configured and consider rate limiting and caching strategies.
    """)
    
    # System status
    st.subheader("🔧 System Status")
    
    try:
        response = requests.get(f"{API_BASE_URL}/")
        if response.status_code == 200:
            st.success("API Backend: Online")
        else:
            st.error("API Backend: Error")
    except:
        st.error("API Backend: Offline")

if __name__ == "__main__":
    main()