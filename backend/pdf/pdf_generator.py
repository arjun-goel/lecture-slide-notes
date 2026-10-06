"""
PDF Generator Module for LectureSlide Notes.
Creates clean, professional, publication-quality lecture notes PDFs
using ReportLab (100% open-source, zero paid APIs).
"""

import os
import datetime
from typing import List, Dict, Any, Optional
import logging

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
    PageBreak,
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print total page numbers
    in format: 'Page X of Y'.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748B"))  # Slate-500
        
        # Draw running top rule and header text on page 2+
        if self._pageNumber > 1:
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(40, 755, letter[0] - 40, 755)
            self.drawString(40, 760, "LectureSlide Notes — Study Archive")

        # Bottom footer
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(40, 42, letter[0] - 40, 42)
        
        timestamp_str = datetime.datetime.now().strftime("%B %d, %Y")
        self.drawString(40, 30, f"Generated locally with LectureSlide Notes • {timestamp_str}")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 40, 30, page_text)
        self.restoreState()


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS string."""
    seconds = int(round(seconds))
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def generate_lecture_pdf(
    lecture_title: str,
    youtube_url: str,
    slides: List[Dict[str, Any]],
    output_pdf_path: str,
    include_ocr: bool = True
) -> str:
    """
    Generates a structured, beautifully formatted PDF document
    containing all curated lecture slides and optional OCR transcripts.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)

    # Document geometry: Letter size with 40pt (0.55in) margins
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=45,
        bottomMargin=50
    )

    available_width = letter[0] - 80  # ~532 points (~7.4 inches)
    story = []

    # Styles
    base_styles = getSampleStyleSheet()

    header_title_style = ParagraphStyle(
        'HeaderTitle',
        parent=base_styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#0F172A'),  # Slate-900
        spaceAfter=6
    )

    header_subtitle_style = ParagraphStyle(
        'HeaderSubtitle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#475569'),  # Slate-600
        spaceAfter=12
    )

    meta_label_style = ParagraphStyle(
        'MetaLabel',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1E293B'),
    )

    meta_value_style = ParagraphStyle(
        'MetaValue',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155'),
    )

    slide_heading_style = ParagraphStyle(
        'SlideHeading',
        parent=base_styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1E293B'),  # Slate-800
        spaceAfter=4
    )

    ocr_title_style = ParagraphStyle(
        'OCRTitle',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#4338CA'),  # Indigo-700
        spaceAfter=3
    )

    ocr_text_style = ParagraphStyle(
        'OCRText',
        parent=base_styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B'),
    )

    # 1. Title & Header Block
    story.append(Paragraph("LECTURE NOTES", ParagraphStyle(
        'SuperTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#4F46E5'),  # Indigo-600
        spaceAfter=4
    )))
    clean_title = (lecture_title or "Untitled Lecture").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    story.append(Paragraph(clean_title, header_title_style))

    # Meta Table Box
    now_str = datetime.datetime.now().strftime("%B %d, %Y • %I:%M %p")
    url_display = youtube_url if len(youtube_url) < 65 else youtube_url[:62] + "..."
    
    meta_data = [
        [
            Paragraph("<b>Source URL:</b>", meta_label_style),
            Paragraph(f"<font color='#2563EB'>{url_display}</font>", meta_value_style),
            Paragraph("<b>Total Slides:</b>", meta_label_style),
            Paragraph(f"<b>{len(slides)}</b> unique slides", meta_value_style),
        ],
        [
            Paragraph("<b>Generated:</b>", meta_label_style),
            Paragraph(now_str, meta_value_style),
            Paragraph("<b>Engine:</b>", meta_label_style),
            Paragraph("LectureSlide Notes (FOSS)", meta_value_style),
        ]
    ]

    meta_table = Table(meta_data, colWidths=[75, available_width - 235, 75, 85])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#F1F5F9')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=14))

    # 2. Iterate each slide
    for idx, slide in enumerate(slides, start=1):
        slide_elements = []
        
        timestamp_sec = slide.get('timestamp', 0.0)
        time_formatted = format_timestamp(timestamp_sec)
        
        # Slide Header: "Slide 01 • Timestamp: 04:32"
        slide_title = f"Slide {idx:02d} &nbsp;&nbsp;<font color='#64748B' size='9'>[Timestamp: {time_formatted}]</font>"
        slide_elements.append(Paragraph(slide_title, slide_heading_style))
        slide_elements.append(Spacer(1, 4))

        # Slide Image
        img_path = slide.get('image_path')
        if img_path and os.path.exists(img_path):
            try:
                with PILImage.open(img_path) as pil_img:
                    orig_w, orig_h = pil_img.size
                
                # Calculate display dimensions preserving aspect ratio
                # Set target display width to available width (~532pt) or suitable max height (~280pt)
                display_w = available_width
                display_h = (orig_h / orig_w) * display_w
                if display_h > 290:
                    display_h = 290
                    display_w = (orig_w / orig_h) * display_h

                rl_img = RLImage(img_path, width=display_w, height=display_h)
                
                # Wrap image in styled border container table
                img_container = Table([[rl_img]], colWidths=[available_width])
                img_container.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0F172A')),
                    ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#CBD5E1')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                slide_elements.append(img_container)
            except Exception as img_err:
                logger.error(f"Error rendering image for slide #{idx}: {img_err}")
                slide_elements.append(Paragraph(f"[Image load error: {img_err}]", meta_value_style))

        # OCR Text Section (if enabled and present)
        ocr_text = slide.get('ocr_text', '').strip()
        if include_ocr and ocr_text:
            slide_elements.append(Spacer(1, 6))
            # Format text lines
            escaped_text = (
                ocr_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
            )
            # Truncate if exceptionally long to prevent single slide overflow
            if len(escaped_text) > 1200:
                escaped_text = escaped_text[:1200] + "... [truncated]"

            ocr_box_content = [
                [Paragraph("EXTRACTED SLIDE TEXT (OCR)", ocr_title_style)],
                [Paragraph(escaped_text, ocr_text_style)]
            ]
            ocr_table = Table(ocr_box_content, colWidths=[available_width])
            ocr_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            slide_elements.append(ocr_table)

        slide_elements.append(Spacer(1, 14))
        # Keep together if space permits, otherwise page break
        story.append(KeepTogether(slide_elements))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=14))

    # Build document using dynamic NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    logger.info(f"PDF generated successfully at {output_pdf_path} ({len(slides)} slides)")
    return output_pdf_path
