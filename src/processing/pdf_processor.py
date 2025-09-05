import aiohttp
import pytesseract
from pdf2image import convert_from_bytes
import fitz  # PyMuPDF
from typing import Optional, Dict, List
from dataclasses import dataclass
import logging
import re
from PIL import Image
from bs4 import BeautifulSoup
import io

logger = logging.getLogger(__name__)

logging.getLogger('pdfminer.pdfinterp').setLevel(logging.ERROR)

@dataclass
class ExtractedContent:
    """Structure for extracted PDF content"""
    text: str
    metadata: Dict
    sections: List[str]
    references: List[str]
    
class PDFProcessor:
    """Advanced PDF processing with OCR capabilities using PyMuPDF"""
    
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
    
    async def process_pdf_from_url(self, pdf_url: str) -> Optional[ExtractedContent]:
        """Download and process PDF from URL"""
        try:
            async with self.session.get(pdf_url) as response:
                if response.status == 200:
                    pdf_content = await response.read()
                    return await self.process_pdf_content(pdf_content)
                else:
                    logger.error(f"Failed to download PDF: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading PDF from {pdf_url}: {e}")
            return None
    
    async def process_pdf_file(self, pdf_path: str) -> Optional[ExtractedContent]:
        """Process PDF from file path"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_content = file.read()
            return await self.process_pdf_content(pdf_content)
        except Exception as e:
            logger.error(f"Error processing PDF file {pdf_path}: {e}")
            return None
    
    async def process_pdf_content(self, pdf_content: bytes) -> Optional[ExtractedContent]:
        """Main PDF processing function"""
        try:
            # Try text extraction first
            extracted = await self.extract_text_based(pdf_content)
            
            # If text extraction fails or yields poor results, use OCR/HTML
            if not extracted:
                logger.info("Text extraction failed/poor quality, trying HTML...")
                extracted = await self.extract_html_content(pdf_content)
                if not extracted:
                    logger.info("HTML extraction failed/poor quality, trying OCR...")
                    extracted = await self.extract_with_ocr(pdf_content)

            if extracted:
                # Post-process the extracted content
                extracted = await self.post_process_content(extracted)
            
            return extracted
            
        except Exception as e:
            logger.error(f"Error processing PDF content: {e}")
            return None
    
    async def extract_text_based(self, pdf_content: bytes) -> Optional[ExtractedContent]:
        """Extract text from text-based PDFs using PyMuPDF"""
        try:
            metadata = {}
            sections = []
            tables = []
            final_text = ""
            
            # Open PDF with fitz
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            try:
                # Extract metadata
                metadata.update({
                    'title': doc.metadata.get('title', 'Unknown Title'),
                    'author': doc.metadata.get('author', ''),
                    'subject': doc.metadata.get('subject', ''),
                    'creator': doc.metadata.get('creator', ''),
                    'producer': doc.metadata.get('producer', ''),
                    'creation_date': doc.metadata.get('creationDate', ''),
                    'modification_date': doc.metadata.get('modDate', ''),
                    'pages': doc.page_count,
                    'extraction_method': 'Text-based (PyMuPDF)'
                })
                
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    
                    # Extract text with layout preservation
                    page_text = page.get_text("text")
                    
                    if page_text:
                        final_text += page_text + "\n"
                        
                        # Extract tables using text blocks
                        page_tables = self.extract_tables_from_page(page)
                        for table in page_tables:
                            tables.append({
                                'content': table,
                                'page_number': page_num + 1
                            })
                
                # Add table information to metadata
                metadata['table_count'] = len(tables)
                metadata['tables'] = tables
                
            finally:
                doc.close()
            
            if len(final_text.strip()) < 200:
                return None
                
            # Extract sections and references
            sections = self.extract_sections(final_text)
            references = self.extract_references(final_text)
            
            return ExtractedContent(
                text=final_text,
                metadata=metadata,
                sections=sections,
                references=references
            )
            
        except Exception as e:
            logger.error(f"Text-based extraction error: {e}")
            return None
    
    def extract_tables_from_page(self, page) -> List[List[List[str]]]:
        """Extract tables from a fitz page using text blocks"""
        tables = []
        
        try:
            # Get text with detailed information
            blocks = page.get_text("dict")["blocks"]
            
            # Simple table detection based on aligned text blocks
            table_candidates = []
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            # Look for patterns that might indicate tabular data
                            text = span["text"].strip()
                            if text and (
                                len(text.split()) > 2 and 
                                any(char.isdigit() for char in text) and
                                "|" in text or "\t" in text or "  " in text
                            ):
                                table_candidates.append(text)
            
            # Process candidates into table structure
            if table_candidates:
                # Simple processing - split by common separators
                for candidate in table_candidates[:3]:  # Limit to 3 tables per page
                    if "|" in candidate:
                        rows = [row.split("|") for row in candidate.split("\n") if row.strip()]
                    elif "\t" in candidate:
                        rows = [row.split("\t") for row in candidate.split("\n") if row.strip()]
                    else:
                        # Split by multiple spaces
                        rows = [re.split(r'\s{2,}', row) for row in candidate.split("\n") if row.strip()]
                    
                    if len(rows) > 1 and all(len(row) > 1 for row in rows):
                        tables.append(rows)
            
        except Exception as e:
            logger.warning(f"Table extraction error on page: {e}")
        
        return tables
    
    async def extract_with_ocr(self, pdf_content: bytes) -> Optional[ExtractedContent]:
        """Extract text using OCR for scanned PDFs"""
        try:
            # Convert PDF to images
            images = convert_from_bytes(
                pdf_content,
                dpi=300,  # High DPI for better OCR
                fmt='jpeg'
            )
            
            all_text = ""
            sections = []
            figures = []
            
            for page_num, image in enumerate(images):
                # Preprocess image for better OCR
                processed_image = self.preprocess_image_for_ocr(image)
                
                # Extract text with OCR
                page_text = pytesseract.image_to_string(
                    processed_image,
                    lang=self.config.ocr_language,
                    config='--psm 6'  # Uniform block of text
                )
                
                all_text += page_text + f"\n--- Page {page_num + 1} ---\n"
                
                # Try to identify figures/images in the page
                if len(page_text.strip()) < 100:
                    figures.append({
                        'caption': f"Image content on page {page_num + 1}",
                        'page_number': page_num + 1
                    })
            
            if len(all_text.strip()) < 200:
                return None
            
            # Extract structured content
            sections = self.extract_sections(all_text)
            references = self.extract_references(all_text)
            
            metadata = {
                'pages': len(images),
                'extraction_method': 'OCR',
                'title': self.extract_title_from_text(all_text),
                'figures': figures
            }
            
            return ExtractedContent(
                text=all_text,
                metadata=metadata,
                sections=sections,
                references=references 
            )
            
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            return None
        
    async def extract_html_content(self, html_content: bytes, original_url: str = "") -> Optional[ExtractedContent]:
        """Handle HTML content and try to extract PDF URL or text content"""
        try:
            html_text = html_content.decode('utf-8', errors='ignore')
            
            # Extract text content from HTML
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer']):
                element.decompose()
            
            # Extract text
            text = soup.get_text(separator='\n', strip=True)
            
            # Clean up text
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            cleaned_text = '\n'.join(lines)
            
            if len(cleaned_text) < 200:
                return None
            
            # Extract structured content
            sections = self.extract_sections(cleaned_text)
            references = self.extract_references(cleaned_text)
            
            metadata = { 
                'extraction_method': 'HTML',
                'title': self.extract_title_from_text(cleaned_text)
            }
            
            return ExtractedContent(
                text=cleaned_text,
                metadata=metadata,
                sections=sections,
                references=references 
            )
            
        except Exception as e:
            logger.error(f"Failed to handle HTML content: {e}")
            return None
    
    def preprocess_image_for_ocr(self, image: Image.Image) -> Image.Image:
        """Preprocess image to improve OCR accuracy"""
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        
        return image
    
    def extract_sections(self, text: str) -> List[str]:
        """Extract sections based on common patterns."""
        section_patterns = [
            r'^(\d+\.?\s+[A-Z][^.\n]*)',  # Numbered sections
            r'^([A-Z][A-Z\s]{3,})\s*$',   # ALL CAPS headers
            r'^\s*(Abstract|Introduction|Method|Results|Discussion|Conclusion|References)',  # Common academic sections
        ]

        lines = text.split('\n')
        sections = []
        current_lines = []

        def flush_section():
            if current_lines:
                sections.append(" ".join(line.strip() for line in current_lines).strip())

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue  # Skip empty lines

            # Check if this line is a section header
            if any(re.match(pattern, stripped, re.IGNORECASE) for pattern in section_patterns):
                flush_section()
                current_lines.clear()
                current_lines.append(stripped)
            else:
                current_lines.append(stripped)

        flush_section()
        return sections

    def extract_references(self, text: str) -> List[str]:
        """Extract references from the text"""
        references = []
        
        # Look for references section
        ref_pattern = r'(?:References|Bibliography|REFERENCES)\s*(.*?)(?:\n\n|\Z)'
        ref_match = re.search(ref_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if ref_match:
            ref_text = ref_match.group(1)
            
            # Split references by patterns
            ref_items = re.split(r'\n(?=\[\d+\]|\d+\.|\[.*?\])', ref_text)
            
            for ref in ref_items:
                ref = ref.strip()
                if len(ref) > 20:
                    references.append(ref)
        
        return references[:50]  # Limit to prevent overcrowding
    
    def extract_title_from_text(self, text: str) -> str:
        """Extract document title from text"""
        lines = text.split('\n')[:10]  # Check first 10 lines
        
        for line in lines:
            line = line.strip()
            # Title is usually the longest line in the beginning
            if len(line) > 20 and len(line) < 200:
                return line
        
        return "Unknown Title"
    
    async def post_process_content(self, content: ExtractedContent) -> ExtractedContent:
        """Post-process extracted content for better quality"""
        # Clean up text
        cleaned_text = self.clean_text(content.text)
        
        # Update the content
        content.text = cleaned_text
        
        # Add derived metadata
        content.metadata['word_count'] = len(cleaned_text.split())
        content.metadata['section_count'] = len(content.sections)
        content.metadata['reference_count'] = len(content.references)
        
        return content
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Remove page headers/footers patterns
        text = re.sub(r'\n--- Page \d+ ---\n', '\n', text)
        
        # Fix common OCR errors
        text = text.replace('ﬁ', 'fi')
        text = text.replace('ﬂ', 'fl')
        text = text.replace('"', '"')
        text = text.replace('"', '"')
        
        return text.strip()