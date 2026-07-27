#!/usr/bin/env python3
"""
sample_report.py - Professional Sample Report Generator for PlanktoScope

Generates publication-quality PDF reports summarizing segmentation results.

Features:
- Sample metadata and acquisition details
- Statistical summaries with key metrics
- Embedded visualizations (size distribution, heatmap, blur quality)
- Representative object gallery
- Quality assessment metrics
- EcoTaxa-compatible data summary

Usage:
    python3 sample_report.py <tsv_path> [output_pdf_path]

Example:
    python3 sample_report.py /home/pi/data/objects/2025-12-09/A_106/ecotaxa_A_106.tsv

Dependencies:
    pip install matplotlib reportlab pillow pandas

Author: PlanktoScope Project
Version: 1.0.0
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from io import BytesIO

# =============================================================================
# LAZY IMPORTS
# =============================================================================

def _import_deps():
    """Import heavy dependencies only when needed."""
    global pd, plt, np, Image
    global canvas, colors, inch, cm, letter, A4
    global SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    global ParagraphStyle, getSampleStyleSheet, TA_CENTER, TA_LEFT, TA_RIGHT
    global ReportLabImage, PageBreak, HRFlowable
    
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    
    from reportlab.lib import colors
    from reportlab.lib.units import inch, cm
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as ReportLabImage, PageBreak, HRFlowable
    )
    from reportlab.pdfgen import canvas


# =============================================================================
# REPORT GENERATOR CLASS
# =============================================================================

class SampleReportGenerator:
    """
    Generates professional PDF reports for PlanktoScope samples.
    """
    
    def __init__(self, tsv_path, objects_dir=None):
        """
        Initialize report generator.
        
        Args:
            tsv_path: Path to EcoTaxa TSV file
            objects_dir: Directory containing object crops (auto-detected if None)
        """
        _import_deps()
        
        self.tsv_path = Path(tsv_path)
        self.objects_dir = Path(objects_dir) if objects_dir else self.tsv_path.parent
        
        # Load and parse TSV
        self.df = self._load_tsv()
        self.meta = self._extract_metadata()
        self.stats = self._compute_statistics()
        
    def _load_tsv(self):
        """Load TSV file into DataFrame."""
        if not self.tsv_path.exists():
            raise FileNotFoundError(f"TSV not found: {self.tsv_path}")
        
        # Read TSV, skip the type indicator row (row 1)
        df = pd.read_csv(self.tsv_path, sep='\t', skiprows=[1])
        return df
    
    def _extract_metadata(self):
        """Extract sample metadata from first row."""
        if len(self.df) == 0:
            return {}
        
        row = self.df.iloc[0]
        return {
            'sample_id': row.get('sample_id', 'Unknown'),
            'project': row.get('sample_project', 'Unknown'),
            'acq_id': row.get('acq_id', 'Unknown'),
            'date': row.get('object_date', 'Unknown'),
            'pixel_size': row.get('process_pixel', 0.94),
        }
    
    def _compute_statistics(self):
        """Compute summary statistics."""
        stats = {
            'total_objects': len(self.df),
            'total_images': self.df['object_time'].nunique() if 'object_time' in self.df else 0,
        }
        
        # Size statistics
        if 'object_area' in self.df:
            stats['area_mean'] = self.df['object_area'].mean()
            stats['area_std'] = self.df['object_area'].std()
            stats['area_min'] = self.df['object_area'].min()
            stats['area_max'] = self.df['object_area'].max()
        
        if 'object_equivalent_diameter' in self.df:
            stats['esd_mean'] = self.df['object_equivalent_diameter'].mean()
            stats['esd_std'] = self.df['object_equivalent_diameter'].std()
            stats['esd_median'] = self.df['object_equivalent_diameter'].median()
        
        # Morphology statistics
        if 'object_elongation' in self.df:
            stats['elongation_mean'] = self.df['object_elongation'].mean()
        
        if 'object_circ.' in self.df:
            stats['circularity_mean'] = self.df['object_circ.'].mean()
        
        if 'object_solidity' in self.df:
            stats['solidity_mean'] = self.df['object_solidity'].mean()
        
        # Blur statistics (if available)
        if 'object_blur_score' in self.df:
            stats['blur_mean'] = self.df['object_blur_score'].mean()
            stats['blur_std'] = self.df['object_blur_score'].std()
            stats['pct_sharp'] = (self.df['object_blur_score'] >= 35).mean() * 100
            stats['pct_blurry'] = (self.df['object_blur_score'] < 35).mean() * 100
        
        return stats
    
    def _create_size_distribution_plot(self):
        """Create ESD histogram plot."""
        fig, ax = plt.subplots(figsize=(6, 3), dpi=150)
        
        if 'object_equivalent_diameter' in self.df:
            data = self.df['object_equivalent_diameter'].dropna()
            ax.hist(data, bins=30, color='#1976D2', edgecolor='white', alpha=0.8)
            ax.axvline(data.median(), color='#D32F2F', linestyle='--', 
                      label=f'Median: {data.median():.1f}')
            ax.set_xlabel('Equivalent Spherical Diameter (px)')
            ax.set_ylabel('Count')
            ax.set_title('Size Distribution')
            ax.legend()
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Save to bytes
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_heatmap_plot(self):
        """Create spatial distribution heatmap."""
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        
        if 'object_x' in self.df and 'object_y' in self.df:
            x = self.df['object_x'].dropna()
            y = self.df['object_y'].dropna()
            
            h = ax.hist2d(x, y, bins=50, cmap='Blues')
            plt.colorbar(h[3], ax=ax, label='Object Count')
            ax.set_xlabel('X Position (px)')
            ax.set_ylabel('Y Position (px)')
            ax.set_title('Spatial Distribution (Flowcell Coverage)')
            ax.invert_yaxis()
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_blur_distribution_plot(self):
        """Create blur score distribution plot."""
        if 'object_blur_score' not in self.df:
            return None
        
        fig, ax = plt.subplots(figsize=(6, 3), dpi=150)
        
        data = self.df['object_blur_score'].dropna()
        
        # Color bars by quality
        n, bins, patches = ax.hist(data, bins=25, edgecolor='white', alpha=0.8)
        
        for i, patch in enumerate(patches):
            bin_center = (bins[i] + bins[i+1]) / 2
            if bin_center < 35:
                patch.set_facecolor('#F44336')  # Red - blurry
            elif bin_center < 60:
                patch.set_facecolor('#FF9800')  # Orange - moderate
            else:
                patch.set_facecolor('#4CAF50')  # Green - sharp
        
        ax.axvline(35, color='#D32F2F', linestyle='--', label='Blur Threshold')
        ax.set_xlabel('Blur Score (0=blurry, 100=sharp)')
        ax.set_ylabel('Count')
        ax.set_title('Focus Quality Distribution')
        ax.legend()
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_morphology_scatter(self):
        """Create morphology scatter plot."""
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        
        if 'object_area' in self.df and 'object_elongation' in self.df:
            area = self.df['object_area'].dropna()
            elong = self.df['object_elongation'].dropna()
            
            # Color by circularity if available
            if 'object_circ.' in self.df:
                circ = self.df['object_circ.'].dropna()
                scatter = ax.scatter(area, elong, c=circ, cmap='viridis', 
                                    alpha=0.6, s=20)
                plt.colorbar(scatter, ax=ax, label='Circularity')
            else:
                ax.scatter(area, elong, alpha=0.6, s=20, color='#1976D2')
            
            ax.set_xlabel('Area (px²)')
            ax.set_ylabel('Elongation')
            ax.set_title('Morphology Space')
            ax.set_xscale('log')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _get_representative_objects(self, n=12):
        """Select representative objects for gallery."""
        objects = []
        
        # Sort by different criteria to get diverse selection
        if len(self.df) == 0:
            return objects
        
        # Largest objects
        if 'object_area' in self.df:
            largest = self.df.nlargest(3, 'object_area')
            for _, row in largest.iterrows():
                objects.append(('Largest', row))
        
        # Sharpest objects (if blur available)
        if 'object_blur_score' in self.df:
            sharpest = self.df.nlargest(3, 'object_blur_score')
            for _, row in sharpest.iterrows():
                objects.append(('Sharpest', row))
        
        # Most circular
        if 'object_circ.' in self.df:
            circular = self.df.nlargest(3, 'object_circ.')
            for _, row in circular.iterrows():
                objects.append(('Circular', row))
        
        # Most elongated
        if 'object_elongation' in self.df:
            elongated = self.df.nlargest(3, 'object_elongation')
            for _, row in elongated.iterrows():
                objects.append(('Elongated', row))
        
        return objects[:n]
    
    def generate_pdf(self, output_path=None):
        """
        Generate the PDF report.
        
        Args:
            output_path: Output PDF path (auto-generated if None)
            
        Returns:
            Path to generated PDF
        """
        if output_path is None:
            output_path = self.tsv_path.parent / f"report_{self.meta['sample_id']}_{self.meta['acq_id']}.pdf"
        
        output_path = Path(output_path)
        
        # Create document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1976D2')
        )
        
        section_style = ParagraphStyle(
            'Section',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#333333')
        )
        
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=8
        )
        
        # Build content
        story = []
        
        # Title
        story.append(Paragraph("PlanktoScope Sample Report", title_style))
        story.append(Spacer(1, 10))
        
        # Generation timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story.append(Paragraph(f"Generated: {timestamp}", 
                              ParagraphStyle('Timestamp', parent=body_style, 
                                           alignment=TA_CENTER, textColor=colors.gray)))
        story.append(Spacer(1, 20))
        
        # Horizontal line
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1976D2')))
        story.append(Spacer(1, 20))
        
        # =====================================================================
        # SAMPLE INFORMATION
        # =====================================================================
        story.append(Paragraph("Sample Information", section_style))
        
        info_data = [
            ['Project:', self.meta.get('project', 'N/A')],
            ['Sample ID:', self.meta.get('sample_id', 'N/A')],
            ['Acquisition:', self.meta.get('acq_id', 'N/A')],
            ['Date:', self.meta.get('date', 'N/A')],
            ['Pixel Size:', f"{self.meta.get('pixel_size', 0.94):.2f} µm/px"],
        ]
        
        info_table = Table(info_data, colWidths=[1.5*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))
        
        # =====================================================================
        # SUMMARY STATISTICS
        # =====================================================================
        story.append(Paragraph("Summary Statistics", section_style))
        
        stats_data = [
            ['Metric', 'Value'],
            ['Total Objects', f"{self.stats['total_objects']:,}"],
            ['Total Images', f"{self.stats.get('total_images', 'N/A')}"],
        ]
        
        if 'esd_mean' in self.stats:
            stats_data.append(['Mean ESD', f"{self.stats['esd_mean']:.1f} ± {self.stats['esd_std']:.1f} px"])
            stats_data.append(['Median ESD', f"{self.stats['esd_median']:.1f} px"])
        
        if 'area_mean' in self.stats:
            stats_data.append(['Mean Area', f"{self.stats['area_mean']:.0f} px²"])
            stats_data.append(['Area Range', f"{self.stats['area_min']:.0f} - {self.stats['area_max']:.0f} px²"])
        
        if 'circularity_mean' in self.stats:
            stats_data.append(['Mean Circularity', f"{self.stats['circularity_mean']:.3f}"])
        
        if 'elongation_mean' in self.stats:
            stats_data.append(['Mean Elongation', f"{self.stats['elongation_mean']:.2f}"])
        
        stats_table = Table(stats_data, colWidths=[2.5*inch, 3*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 20))
        
        # =====================================================================
        # QUALITY METRICS (if blur data available)
        # =====================================================================
        if 'blur_mean' in self.stats:
            story.append(Paragraph("Focus Quality Assessment", section_style))
            
            quality_data = [
                ['Metric', 'Value'],
                ['Mean Blur Score', f"{self.stats['blur_mean']:.1f}/100"],
                ['Sharp Objects (≥35)', f"{self.stats['pct_sharp']:.1f}%"],
                ['Blurry Objects (<35)', f"{self.stats['pct_blurry']:.1f}%"],
            ]
            
            # Quality assessment
            if self.stats['pct_sharp'] >= 80:
                quality = "Excellent"
                quality_color = colors.HexColor('#4CAF50')
            elif self.stats['pct_sharp'] >= 60:
                quality = "Good"
                quality_color = colors.HexColor('#8BC34A')
            elif self.stats['pct_sharp'] >= 40:
                quality = "Moderate"
                quality_color = colors.HexColor('#FF9800')
            else:
                quality = "Poor"
                quality_color = colors.HexColor('#F44336')
            
            quality_data.append(['Overall Quality', quality])
            
            quality_table = Table(quality_data, colWidths=[2.5*inch, 3*inch])
            quality_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('BACKGROUND', (1, -1), (1, -1), quality_color),
                ('TEXTCOLOR', (1, -1), (1, -1), colors.white),
                ('FONTNAME', (1, -1), (1, -1), 'Helvetica-Bold'),
            ]))
            story.append(quality_table)
            story.append(Spacer(1, 20))
        
        # =====================================================================
        # VISUALIZATIONS
        # =====================================================================
        story.append(PageBreak())
        story.append(Paragraph("Visualizations", section_style))
        story.append(Spacer(1, 10))
        
        # Size distribution
        try:
            size_plot = self._create_size_distribution_plot()
            story.append(Paragraph("Size Distribution", body_style))
            story.append(ReportLabImage(size_plot, width=5.5*inch, height=2.75*inch))
            story.append(Spacer(1, 15))
        except Exception as e:
            story.append(Paragraph(f"[Size plot error: {e}]", body_style))
        
        # Heatmap
        try:
            heatmap_plot = self._create_heatmap_plot()
            story.append(Paragraph("Spatial Distribution", body_style))
            story.append(ReportLabImage(heatmap_plot, width=5.5*inch, height=3.5*inch))
            story.append(Spacer(1, 15))
        except Exception as e:
            story.append(Paragraph(f"[Heatmap error: {e}]", body_style))
        
        # Blur distribution (if available)
        if 'object_blur_score' in self.df:
            try:
                blur_plot = self._create_blur_distribution_plot()
                if blur_plot:
                    story.append(PageBreak())
                    story.append(Paragraph("Focus Quality Distribution", body_style))
                    story.append(ReportLabImage(blur_plot, width=5.5*inch, height=2.75*inch))
                    story.append(Spacer(1, 15))
            except Exception as e:
                story.append(Paragraph(f"[Blur plot error: {e}]", body_style))
        
        # Morphology scatter
        try:
            morph_plot = self._create_morphology_scatter()
            story.append(Paragraph("Morphology Space", body_style))
            story.append(ReportLabImage(morph_plot, width=5.5*inch, height=3.5*inch))
        except Exception as e:
            story.append(Paragraph(f"[Morphology plot error: {e}]", body_style))
        
        # =====================================================================
        # FOOTER
        # =====================================================================
        story.append(Spacer(1, 30))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "Generated by PlanktoScope Sample Report Generator v1.0",
            ParagraphStyle('Footer', parent=body_style, fontSize=8, 
                          textColor=colors.gray, alignment=TA_CENTER)
        ))
        
        # Build PDF
        doc.build(story)
        
        print(f"Report generated: {output_path}")
        return output_path


# =============================================================================
# CLI
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sample_report.py <tsv_path> [output_pdf_path]")
        print("\nGenerates a professional PDF report from segmentation TSV data.")
        print("\nExample:")
        print("  python3 sample_report.py /home/pi/data/objects/2025-12-09/A_106/ecotaxa_A_106.tsv")
        sys.exit(1)
    
    tsv_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        generator = SampleReportGenerator(tsv_path)
        pdf_path = generator.generate_pdf(output_path)
        print(f"\n✓ Report saved to: {pdf_path}")
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
