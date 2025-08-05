import asyncio
import aiohttp
import pytesseract
from pdf2image import convert_from_bytes, convert_from_path
import PyPDF2
import pdfplumber
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import tempfile
import logging
import re
from PIL import Image
import io

logger = logging.getLogger(__name__)

@dataclass
class ExtractedContent:
    """Structure for extracted PDF content"""
    text: str
    metadata: Dict
    sections: List[Dict]  # Title, content, page_number
    references: List[str]
    figures: List[Dict]   # Caption, page_number
    tables: List[Dict]    # Content, page_number
    
class PDFProcessor:
    """Advanced PDF processing with OCR capabilities"""
    
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
            # Try text extraction first (faster)
            extracted = await self.extract_text_based(pdf_content)
            
            # If text extraction fails or yields poor results, use OCR
            if not extracted or len(extracted.text.strip()) < 100:
                logger.info("Text extraction failed/poor quality, trying OCR...")
                extracted = await self.extract_with_ocr(pdf_content)
            
            if extracted:
                # Post-process the extracted content
                extracted = await self.post_process_content(extracted)
            
            return extracted
            
        except Exception as e:
            logger.error(f"Error processing PDF content: {e}")
            return None
    
    async def extract_text_based(self, pdf_content: bytes) -> Optional[ExtractedContent]:
        """Extract text from text-based PDFs"""
        try:
            # Method 1: PyPDF2 for basic extraction
            text_pypdf2 = ""
            metadata = {}
            
            with io.BytesIO(pdf_content) as pdf_buffer:
                pdf_reader = PyPDF2.PdfReader(pdf_buffer)
                metadata = {
                    'pages': len(pdf_reader.pages),
                    'title': pdf_reader.metadata.get('/Title', '') if pdf_reader.metadata else '',
                    'author': pdf_reader.metadata.get('/Author', '') if pdf_reader.metadata else '',
                }
                
                for page in pdf_reader.pages:
                    text_pypdf2 += page.extract_text() + "\n"
            
            # Method 2: pdfplumber for better structure extraction
            sections = []
            tables = []
            
            with io.BytesIO(pdf_content) as pdf_buffer:
                with pdfplumber.open(pdf_buffer) as pdf:
                    current_text = ""
                    
                    for page_num, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            current_text += page_text + "\n"
                            
                            # Extract tables
                            page_tables = page.extract_tables()
                            for table in page_tables:
                                tables.append({
                                    'content': table,
                                    'page_number': page_num + 1
                                })
            
            # Use the better extraction result
            final_text = current_text if len(current_text) > len(text_pypdf2) else text_pypdf2
            
            if len(final_text.strip()) < 50:
                return None
                
            # Extract sections and references
            sections = self.extract_sections(final_text)
            references = self.extract_references(final_text)
            figures = self.extract_figure_captions(final_text)
            
            return ExtractedContent(
                text=final_text,
                metadata=metadata,
                sections=sections,
                references=references,
                figures=figures,
                tables=tables
            )
            
        except Exception as e:
            logger.error(f"Text-based extraction error: {e}")
            return None
    
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
                if len(page_text.strip()) < 100:  # Likely contains mostly images
                    figures.append({
                        'caption': f"Image content on page {page_num + 1}",
                        'page_number': page_num + 1
                    })
            
            if len(all_text.strip()) < 50:
                return None
            
            # Extract structured content
            sections = self.extract_sections(all_text)
            references = self.extract_references(all_text)
            
            metadata = {
                'pages': len(images),
                'extraction_method': 'OCR',
                'title': self.extract_title_from_text(all_text)
            }
            
            return ExtractedContent(
                text=all_text,
                metadata=metadata,
                sections=sections,
                references=references,
                figures=figures,
                tables=[] 
            )
            
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            return None
    
    def preprocess_image_for_ocr(self, image: Image.Image) -> Image.Image:
        """Preprocess image to improve OCR accuracy"""
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        
        return image
    
    def extract_sections(self, text: str) -> List[Dict]:
        """Extract document sections based on common patterns"""
        sections = []
        
        # Common section headers pattern
        section_patterns = [
            r'^(\d+\.?\s+[A-Z][^.\n]*)',  # Numbered sections
            r'^([A-Z][A-Z\s]{3,})\s*$',   # ALL CAPS headers
            r'^\s*(Abstract|Introduction|Method|Results|Discussion|Conclusion|References)',  # Common academic sections
        ]
        
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            
            # Check if line matches section pattern
            is_section = False
            for pattern in section_patterns:
                if re.match(pattern, line, re.IGNORECASE | re.MULTILINE):
                    # Save previous section
                    if current_section and current_content:
                        sections.append({
                            'title': current_section,
                            'content': '\n'.join(current_content).strip(),
                            'start_line': len(sections)
                        })
                    
                    current_section = line
                    current_content = []
                    is_section = True
                    break
            
            if not is_section and line:
                current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            sections.append({
                'title': current_section,
                'content': '\n'.join(current_content).strip(),
                'start_line': len(sections)
            })
        
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
                if len(ref) > 20:  # Filter out short/invalid references
                    references.append(ref)
        
        return references[:50]  # Limit to prevent overcrowding
    
    def extract_figure_captions(self, text: str) -> List[Dict]:
        """Extract figure captions"""
        figures = []
        
        # Pattern for figure captions
        fig_pattern = r'(Figure?\s+\d+[.:]\s*[^\n]+)'
        matches = re.finditer(fig_pattern, text, re.IGNORECASE)
        
        for match in matches:
            figures.append({
                'caption': match.group(1).strip(),
                'position': match.start()
            })
        
        return figures
    
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
