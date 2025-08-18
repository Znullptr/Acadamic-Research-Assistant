import os
from datetime import datetime
from src.processing.pdf_processor import PDFProcessor
from dataclasses import asdict
import shutil

async def process_pdf_papers(config, vector_store, upload_dir):
    """
    Process PDF files from upload directory and add them to vector store
    
    Args:
        config: Configuration object
        upload_dir: Path to directory containing uploaded PDF files
    
    Returns:
        dict: Processing results with success/failure counts
    """
    processor = PDFProcessor(config)
    results = {
        "success_count": 0,
        "error_count": 0,
        "errors": [],
        "processed_files": []
    }
    
    try:
        # Get list of PDF files in upload directory
        if not os.path.exists(upload_dir):
            raise FileNotFoundError(f"Upload directory {upload_dir} does not exist")
        
        pdf_files = [f for f in os.listdir(upload_dir) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            return {**results, "message": "No PDF files found in upload directory"}
        
        # Process each PDF file
        for filename in pdf_files:
            file_path = os.path.join(upload_dir, filename)
            
            try:
                # Process PDF file
                content= await processor.process_pdf_file(file_path)
                content_dict = asdict(content)
                
                # Get current date
                current_date = datetime.now().isoformat()
                
                # Prepare metadata
                metadata = {
                    "paper_title": content_dict.get("title", filename.replace('.pdf', '')),
                    "paper_id": content_dict.get("url", "User-pv" + filename.replace('.pdf', '')),
                    "pub_date": content_dict.get("pub_date", current_date),
                    "sections": ','.join(content_dict.get("sections", [])) if content_dict.get("sections") else "",
                    "citations": content_dict.get("citations", 0),
                    "venue": content_dict.get("venue", ""),
                    "authors": ",".join(content_dict.get("authors", [])) if content_dict.get("authors") else "",
                    "doi": content_dict.get("doi", ""),
                    "abstract": content_dict.get("abstract", ""),
                    "references": ','.join(content_dict.get("references", [])) if content_dict.get("references") else "",
                    "extraction_method": content_dict.get("metadata", {}).get("extraction_method", "text"),
                }
                
                # Add document to vector store
                await vector_store.add_document(
                    content=content_dict.get("text", ""),
                    metadata=metadata
                )
                
                results["success_count"] += 1
                results["processed_files"].append(filename)
                
            except Exception as e:
                error_msg = f"Error processing {filename}: {str(e)}"
                results["errors"].append(error_msg)
                results["error_count"] += 1
                print(f"Error processing {filename}: {e}")
                continue
        
        # Clean up: remove upload directory and its contents
        try:
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir)
                print(f"Successfully removed upload directory: {upload_dir}")
        except Exception as e:
            print(f"Warning: Could not remove upload directory {upload_dir}: {e}")
        
        return results
        
    except Exception as e:
        results["errors"].append(f"General processing error: {str(e)}")
        results["error_count"] += 1
        return results


