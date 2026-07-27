#!/usr/bin/env python3
"""
sample_report_v2.py - Enhanced Customizable Report Generator for PlanktoScope

Features:
- Configurable report sections via JSON
- Smart representative gallery with clustering
- Least-blurry object selection per cluster
- Multiple visualization options
- Publication-quality PDF output

Usage:
    python3 sample_report_v2.py <tsv_path> [output_pdf_path] [config_path]

Configuration:
    Create a report_config.json file or use --generate-config to create a template.

Author: PlanktoScope Project
Version: 2.0.0
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from io import BytesIO
from collections import defaultdict

# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================

DEFAULT_CONFIG = {
    "report_title": "PlanktoScope Sample Report",
    "sections": {
        "sample_info": True,
        "summary_stats": True,
        "quality_metrics": True,
        "size_distribution": True,
        "spatial_heatmap": True,
        "blur_distribution": True,
        "morphology_scatter": True,
        "temporal_analysis": True,
        "representative_gallery": True,
        "size_class_breakdown": True
    },
    "gallery": {
        "enabled": True,
        "num_clusters": 25,
        "images_per_cluster": 1,
        "prefer_least_blurry": True,
        "min_blur_score": 20,
        "thumbnail_size": 120,
        "clustering_method": "morphology",  # "morphology", "color", "size", "random"
        "show_cluster_stats": True,
        "columns": 5
    },
    "plots": {
        "size_histogram_bins": 30,
        "show_kde": False,
        "color_scheme": "viridis",
        "figure_dpi": 150,
        "show_median_line": True,
        "log_scale_area": True
    },
    "size_classes": {
        "enabled": True,
        "boundaries_um": [10, 20, 50, 100, 200, 500],
        "labels": ["<10µm", "10-20µm", "20-50µm", "50-100µm", "100-200µm", "200-500µm", ">500µm"]
    },
    "output": {
        "page_size": "A4",
        "include_timestamp": True,
        "include_footer": True
    }
}


def generate_default_config(output_path="report_config.json"):
    """Generate a default configuration file."""
    with open(output_path, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"Default configuration saved to: {output_path}")
    return output_path


# =============================================================================
# LAZY IMPORTS
# =============================================================================

def _import_deps():
    """Import heavy dependencies only when needed."""
    global pd, plt, np, Image
    global canvas, colors, inch, cm, letter, A4
    global SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    global ParagraphStyle, getSampleStyleSheet, TA_CENTER, TA_LEFT, TA_RIGHT
    global ReportLabImage, PageBreak, HRFlowable, KeepTogether
    
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
        Image as ReportLabImage, PageBreak, HRFlowable, KeepTogether
    )
    from reportlab.pdfgen import canvas


# =============================================================================
# CLUSTERING UTILITIES
# =============================================================================

class ObjectClusterer:
    """Cluster similar objects for representative gallery selection."""
    
    def __init__(self, df, objects_dir, config):
        self.df = df
        self.objects_dir = Path(objects_dir)
        self.config = config
        
    def cluster_by_morphology(self, n_clusters=25):
        """
        Cluster objects by morphological features.
        Uses simple binning approach (no sklearn dependency).
        """
        if len(self.df) == 0:
            return {}
        
        # Features for clustering
        features = []
        feature_cols = ['object_area', 'object_elongation', 'object_circ.', 'object_solidity']
        available_cols = [c for c in feature_cols if c in self.df.columns]
        
        if not available_cols:
            # Fallback to random clustering
            return self._cluster_random(n_clusters)
        
        # Normalize features to 0-1 range
        df_norm = self.df.copy()
        for col in available_cols:
            col_data = df_norm[col].fillna(df_norm[col].median())
            col_min, col_max = col_data.min(), col_data.max()
            if col_max > col_min:
                df_norm[f'{col}_norm'] = (col_data - col_min) / (col_max - col_min)
            else:
                df_norm[f'{col}_norm'] = 0.5
        
        # Create composite score for binning
        norm_cols = [f'{c}_norm' for c in available_cols]
        df_norm['composite'] = df_norm[norm_cols].mean(axis=1)
        
        # Bin into clusters
        df_norm['cluster'] = pd.cut(df_norm['composite'], bins=n_clusters, labels=False)
        df_norm['cluster'] = df_norm['cluster'].fillna(0).astype(int)
        
        # Group by cluster
        clusters = defaultdict(list)
        for idx, row in df_norm.iterrows():
            cluster_id = int(row['cluster'])
            clusters[cluster_id].append(idx)
        
        return dict(clusters)
    
    def cluster_by_size(self, n_clusters=25):
        """Cluster objects by size (area)."""
        if len(self.df) == 0 or 'object_area' not in self.df.columns:
            return self._cluster_random(n_clusters)
        
        df_sorted = self.df.copy()
        df_sorted['cluster'] = pd.qcut(
            df_sorted['object_area'].rank(method='first'), 
            q=min(n_clusters, len(df_sorted)), 
            labels=False,
            duplicates='drop'
        )
        
        clusters = defaultdict(list)
        for idx, row in df_sorted.iterrows():
            clusters[int(row['cluster'])].append(idx)
        
        return dict(clusters)
    
    def cluster_by_color(self, n_clusters=25):
        """Cluster objects by mean HSV color."""
        if len(self.df) == 0:
            return self._cluster_random(n_clusters)
        
        color_cols = ['object_MeanHue', 'object_MeanSaturation', 'object_MeanValue']
        if not all(c in self.df.columns for c in color_cols):
            return self.cluster_by_morphology(n_clusters)
        
        df_norm = self.df.copy()
        # Normalize hue (0-180) and sat/val (0-255)
        df_norm['hue_norm'] = df_norm['object_MeanHue'].fillna(90) / 180
        df_norm['sat_norm'] = df_norm['object_MeanSaturation'].fillna(128) / 255
        df_norm['val_norm'] = df_norm['object_MeanValue'].fillna(128) / 255
        
        # Weight hue more heavily for color clustering
        df_norm['color_composite'] = (
            df_norm['hue_norm'] * 0.5 + 
            df_norm['sat_norm'] * 0.3 + 
            df_norm['val_norm'] * 0.2
        )
        
        df_norm['cluster'] = pd.cut(df_norm['color_composite'], bins=n_clusters, labels=False)
        df_norm['cluster'] = df_norm['cluster'].fillna(0).astype(int)
        
        clusters = defaultdict(list)
        for idx, row in df_norm.iterrows():
            clusters[int(row['cluster'])].append(idx)
        
        return dict(clusters)
    
    def _cluster_random(self, n_clusters=25):
        """Fallback: randomly assign to clusters."""
        clusters = defaultdict(list)
        for i, idx in enumerate(self.df.index):
            clusters[i % n_clusters].append(idx)
        return dict(clusters)
    
    def get_clusters(self, method='morphology', n_clusters=25):
        """Get clusters using specified method."""
        if method == 'morphology':
            return self.cluster_by_morphology(n_clusters)
        elif method == 'size':
            return self.cluster_by_size(n_clusters)
        elif method == 'color':
            return self.cluster_by_color(n_clusters)
        else:
            return self._cluster_random(n_clusters)
    
    def select_representatives(self, clusters, prefer_least_blurry=True, min_blur=20):
        """
        Select best representative from each cluster.
        Prefers least blurry objects if blur scores available.
        """
        representatives = []
        
        for cluster_id, indices in sorted(clusters.items()):
            if not indices:
                continue
            
            cluster_df = self.df.loc[indices]
            
            # Filter by minimum blur score if available
            if 'object_blur_score' in cluster_df.columns and prefer_least_blurry:
                good_blur = cluster_df[cluster_df['object_blur_score'] >= min_blur]
                if len(good_blur) > 0:
                    # Select sharpest from this cluster
                    best_idx = good_blur['object_blur_score'].idxmax()
                else:
                    # No objects meet blur threshold, take the best available
                    best_idx = cluster_df['object_blur_score'].idxmax()
            else:
                # No blur data, select by largest area (typically better quality)
                if 'object_area' in cluster_df.columns:
                    best_idx = cluster_df['object_area'].idxmax()
                else:
                    best_idx = indices[0]
            
            row = self.df.loc[best_idx]
            representatives.append({
                'cluster_id': cluster_id,
                'cluster_size': len(indices),
                'index': best_idx,
                'row': row
            })
        
        # Sort by cluster size (most prevalent first)
        representatives.sort(key=lambda x: x['cluster_size'], reverse=True)
        
        return representatives


# =============================================================================
# REPORT GENERATOR CLASS
# =============================================================================

class EnhancedReportGenerator:
    """
    Enhanced PDF report generator with customizable sections and smart galleries.
    """
    
    def __init__(self, tsv_path, objects_dir=None, config=None):
        """
        Initialize report generator.
        
        Args:
            tsv_path: Path to EcoTaxa TSV file
            objects_dir: Directory containing object crops (auto-detected if None)
            config: Configuration dict or path to JSON config file
        """
        _import_deps()
        
        self.tsv_path = Path(tsv_path)
        self.objects_dir = Path(objects_dir) if objects_dir else self.tsv_path.parent
        
        # Load configuration
        self.config = self._load_config(config)
        
        # Load and parse TSV
        self.df = self._load_tsv()
        self.meta = self._extract_metadata()
        self.stats = self._compute_statistics()
        
        # Initialize clusterer for gallery
        self.clusterer = ObjectClusterer(self.df, self.objects_dir, self.config)
    
    def _load_config(self, config):
        """Load configuration from dict, file, or use defaults."""
        if config is None:
            return DEFAULT_CONFIG.copy()
        
        if isinstance(config, dict):
            merged = DEFAULT_CONFIG.copy()
            self._deep_update(merged, config)
            return merged
        
        if isinstance(config, (str, Path)):
            config_path = Path(config)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    loaded = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                self._deep_update(merged, loaded)
                return merged
        
        return DEFAULT_CONFIG.copy()
    
    def _deep_update(self, base, update):
        """Recursively update nested dict."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
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
            'pixel_size': float(row.get('process_pixel', 0.94)),
        }
    
    def _compute_statistics(self):
        """Compute comprehensive summary statistics."""
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
            stats['area_median'] = self.df['object_area'].median()
        
        if 'object_equivalent_diameter' in self.df:
            pixel_size = self.meta.get('pixel_size', 0.94)
            esd_um = self.df['object_equivalent_diameter'] * pixel_size
            stats['esd_mean'] = self.df['object_equivalent_diameter'].mean()
            stats['esd_std'] = self.df['object_equivalent_diameter'].std()
            stats['esd_median'] = self.df['object_equivalent_diameter'].median()
            stats['esd_um_mean'] = esd_um.mean()
            stats['esd_um_median'] = esd_um.median()
        
        # Morphology statistics
        if 'object_elongation' in self.df:
            stats['elongation_mean'] = self.df['object_elongation'].mean()
            stats['elongation_median'] = self.df['object_elongation'].median()
        
        if 'object_circ.' in self.df:
            stats['circularity_mean'] = self.df['object_circ.'].mean()
        
        if 'object_solidity' in self.df:
            stats['solidity_mean'] = self.df['object_solidity'].mean()
        
        # Blur statistics
        if 'object_blur_score' in self.df:
            stats['blur_mean'] = self.df['object_blur_score'].mean()
            stats['blur_std'] = self.df['object_blur_score'].std()
            stats['blur_median'] = self.df['object_blur_score'].median()
            stats['pct_sharp'] = (self.df['object_blur_score'] >= 35).mean() * 100
            stats['pct_moderate'] = ((self.df['object_blur_score'] >= 20) & 
                                     (self.df['object_blur_score'] < 35)).mean() * 100
            stats['pct_blurry'] = (self.df['object_blur_score'] < 20).mean() * 100
        
        # Size class distribution
        if self.config['size_classes']['enabled'] and 'object_equivalent_diameter' in self.df:
            stats['size_classes'] = self._compute_size_classes()
        
        return stats
    
    def _compute_size_classes(self):
        """Compute size class distribution."""
        pixel_size = self.meta.get('pixel_size', 0.94)
        boundaries = self.config['size_classes']['boundaries_um']
        labels = self.config['size_classes']['labels']
        
        # Convert ESD to µm
        esd_um = self.df['object_equivalent_diameter'] * pixel_size
        
        # Count in each class
        counts = []
        prev_bound = 0
        for i, bound in enumerate(boundaries):
            count = ((esd_um >= prev_bound) & (esd_um < bound)).sum()
            counts.append(count)
            prev_bound = bound
        
        # Last class (> last boundary)
        counts.append((esd_um >= boundaries[-1]).sum())
        
        return dict(zip(labels, counts))
    
    # =========================================================================
    # PLOT GENERATION
    # =========================================================================
    
    def _create_size_distribution_plot(self):
        """Create ESD histogram plot."""
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(6, 3), dpi=plot_cfg['figure_dpi'])
        
        if 'object_equivalent_diameter' in self.df:
            data = self.df['object_equivalent_diameter'].dropna()
            pixel_size = self.meta.get('pixel_size', 0.94)
            data_um = data * pixel_size
            
            ax.hist(data_um, bins=plot_cfg['size_histogram_bins'], 
                   color='#1976D2', edgecolor='white', alpha=0.8)
            
            if plot_cfg['show_median_line']:
                ax.axvline(data_um.median(), color='#D32F2F', linestyle='--', 
                          linewidth=2, label=f'Median: {data_um.median():.1f} µm')
                ax.legend()
            
            ax.set_xlabel('Equivalent Spherical Diameter (µm)')
            ax.set_ylabel('Count')
            ax.set_title('Size Distribution')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_size_class_pie(self):
        """Create size class pie chart."""
        if 'size_classes' not in self.stats:
            return None
        
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(5, 4), dpi=plot_cfg['figure_dpi'])
        
        size_classes = self.stats['size_classes']
        labels = [k for k, v in size_classes.items() if v > 0]
        sizes = [v for v in size_classes.values() if v > 0]
        
        if not sizes:
            plt.close(fig)
            return None
        
        colors_list = plt.cm.get_cmap(plot_cfg['color_scheme'])(
            np.linspace(0.2, 0.8, len(sizes))
        )
        
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct='%1.1f%%',
            colors=colors_list, startangle=90
        )
        ax.set_title('Size Class Distribution')
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_heatmap_plot(self):
        """Create spatial distribution heatmap."""
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(6, 4), dpi=plot_cfg['figure_dpi'])
        
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
        
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(6, 3), dpi=plot_cfg['figure_dpi'])
        
        data = self.df['object_blur_score'].dropna()
        
        n, bins, patches = ax.hist(data, bins=25, edgecolor='white', alpha=0.8)
        
        for i, patch in enumerate(patches):
            bin_center = (bins[i] + bins[i+1]) / 2
            if bin_center < 20:
                patch.set_facecolor('#F44336')  # Red - very blurry
            elif bin_center < 35:
                patch.set_facecolor('#FF9800')  # Orange - moderate
            else:
                patch.set_facecolor('#4CAF50')  # Green - sharp
        
        ax.axvline(20, color='#F44336', linestyle='--', alpha=0.7, label='Blurry threshold')
        ax.axvline(35, color='#4CAF50', linestyle='--', alpha=0.7, label='Sharp threshold')
        ax.set_xlabel('Blur Score (0=blurry, 100=sharp)')
        ax.set_ylabel('Count')
        ax.set_title('Focus Quality Distribution')
        ax.legend(fontsize=8)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_morphology_scatter(self):
        """Create morphology scatter plot."""
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(6, 4), dpi=plot_cfg['figure_dpi'])
        
        if 'object_area' in self.df and 'object_elongation' in self.df:
            area = self.df['object_area'].dropna()
            elong = self.df['object_elongation'].dropna()
            
            # Align indices
            common_idx = area.index.intersection(elong.index)
            area = area.loc[common_idx]
            elong = elong.loc[common_idx]
            
            if 'object_circ.' in self.df:
                circ = self.df.loc[common_idx, 'object_circ.'].fillna(0.5)
                scatter = ax.scatter(area, elong, c=circ, 
                                    cmap=plot_cfg['color_scheme'], 
                                    alpha=0.6, s=20)
                plt.colorbar(scatter, ax=ax, label='Circularity')
            else:
                ax.scatter(area, elong, alpha=0.6, s=20, color='#1976D2')
            
            ax.set_xlabel('Area (px²)')
            ax.set_ylabel('Elongation')
            ax.set_title('Morphology Space')
            if plot_cfg['log_scale_area']:
                ax.set_xscale('log')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    def _create_temporal_plot(self):
        """Create objects over time plot."""
        if 'object_time' not in self.df:
            return None
        
        plot_cfg = self.config['plots']
        fig, ax = plt.subplots(figsize=(6, 3), dpi=plot_cfg['figure_dpi'])
        
        # Count objects per timestamp
        time_counts = self.df.groupby('object_time').size()
        
        if len(time_counts) > 1:
            ax.plot(range(len(time_counts)), time_counts.values, 
                   color='#1976D2', linewidth=1.5)
            ax.fill_between(range(len(time_counts)), time_counts.values, 
                           alpha=0.3, color='#1976D2')
            ax.set_xlabel('Frame Number')
            ax.set_ylabel('Objects per Frame')
            ax.set_title('Temporal Distribution')
            
            # Add mean line
            mean_count = time_counts.mean()
            ax.axhline(mean_count, color='#D32F2F', linestyle='--', 
                      label=f'Mean: {mean_count:.1f}')
            ax.legend()
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf
    
    # =========================================================================
    # GALLERY GENERATION
    # =========================================================================
    
    def _create_representative_gallery(self):
        """
        Create gallery of representative objects.
        Returns list of (image_path, cluster_info) tuples.
        """
        gallery_cfg = self.config['gallery']
        
        if not gallery_cfg['enabled'] or len(self.df) == 0:
            return []
        
        # Get clusters
        clusters = self.clusterer.get_clusters(
            method=gallery_cfg['clustering_method'],
            n_clusters=gallery_cfg['num_clusters']
        )
        
        # Select representatives
        representatives = self.clusterer.select_representatives(
            clusters,
            prefer_least_blurry=gallery_cfg['prefer_least_blurry'],
            min_blur=gallery_cfg['min_blur_score']
        )
        
        # Load images
        gallery_items = []
        for rep in representatives[:gallery_cfg['num_clusters']]:
            row = rep['row']
            img_filename = row.get('img_file_name', '')
            
            if not img_filename:
                continue
            
            img_path = self.objects_dir / img_filename
            if not img_path.exists():
                continue
            
            # Get stats for this object
            obj_stats = {
                'cluster_id': rep['cluster_id'],
                'cluster_size': rep['cluster_size'],
                'pct_of_total': (rep['cluster_size'] / len(self.df)) * 100,
            }
            
            if 'object_blur_score' in row:
                obj_stats['blur_score'] = row['object_blur_score']
            if 'object_equivalent_diameter' in row:
                pixel_size = self.meta.get('pixel_size', 0.94)
                obj_stats['esd_um'] = row['object_equivalent_diameter'] * pixel_size
            if 'object_area' in row:
                obj_stats['area'] = row['object_area']
            
            gallery_items.append({
                'path': img_path,
                'stats': obj_stats,
                'row': row
            })
        
        return gallery_items
    
    def _create_gallery_grid_image(self, gallery_items):
        """Create a grid image of gallery thumbnails."""
        gallery_cfg = self.config['gallery']
        thumb_size = gallery_cfg['thumbnail_size']
        columns = gallery_cfg['columns']
        
        if not gallery_items:
            return None
        
        n_items = len(gallery_items)
        rows = (n_items + columns - 1) // columns
        
        # Create grid
        grid_width = columns * (thumb_size + 10) + 10
        grid_height = rows * (thumb_size + 30) + 10
        
        grid = Image.new('RGB', (grid_width, grid_height), 'white')
        
        for i, item in enumerate(gallery_items):
            row_idx = i // columns
            col_idx = i % columns
            
            x = 10 + col_idx * (thumb_size + 10)
            y = 10 + row_idx * (thumb_size + 30)
            
            try:
                img = Image.open(item['path'])
                img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
                
                # Center in cell
                paste_x = x + (thumb_size - img.width) // 2
                paste_y = y + (thumb_size - img.height) // 2
                
                grid.paste(img, (paste_x, paste_y))
            except Exception as e:
                # Draw placeholder
                pass
        
        buf = BytesIO()
        grid.save(buf, format='PNG')
        buf.seek(0)
        return buf
    
    # =========================================================================
    # PDF GENERATION
    # =========================================================================
    
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
        sections = self.config['sections']
        
        # Page size
        page_size = A4 if self.config['output']['page_size'] == 'A4' else letter
        
        # Create document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=page_size,
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
        
        caption_style = ParagraphStyle(
            'Caption',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.gray,
            alignment=TA_CENTER
        )
        
        # Build content
        story = []
        
        # Title
        story.append(Paragraph(self.config['report_title'], title_style))
        story.append(Spacer(1, 10))
        
        # Generation timestamp
        if self.config['output']['include_timestamp']:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            story.append(Paragraph(f"Generated: {timestamp}", 
                                  ParagraphStyle('Timestamp', parent=body_style, 
                                               alignment=TA_CENTER, textColor=colors.gray)))
        story.append(Spacer(1, 20))
        
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1976D2')))
        story.append(Spacer(1, 20))
        
        # =====================================================================
        # SAMPLE INFORMATION
        # =====================================================================
        if sections.get('sample_info', True):
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
        if sections.get('summary_stats', True):
            story.append(Paragraph("Summary Statistics", section_style))
            
            stats_data = [
                ['Metric', 'Value'],
                ['Total Objects', f"{self.stats['total_objects']:,}"],
                ['Total Images', f"{self.stats.get('total_images', 'N/A')}"],
            ]
            
            if 'esd_um_mean' in self.stats:
                stats_data.append(['Mean ESD', f"{self.stats['esd_um_mean']:.1f} µm"])
                stats_data.append(['Median ESD', f"{self.stats['esd_um_median']:.1f} µm"])
            elif 'esd_mean' in self.stats:
                stats_data.append(['Mean ESD', f"{self.stats['esd_mean']:.1f} ± {self.stats['esd_std']:.1f} px"])
            
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
        # QUALITY METRICS
        # =====================================================================
        if sections.get('quality_metrics', True) and 'blur_mean' in self.stats:
            story.append(Paragraph("Focus Quality Assessment", section_style))
            
            quality_data = [
                ['Metric', 'Value'],
                ['Mean Blur Score', f"{self.stats['blur_mean']:.1f}/100"],
                ['Median Blur Score', f"{self.stats['blur_median']:.1f}/100"],
                ['Sharp Objects (≥35)', f"{self.stats['pct_sharp']:.1f}%"],
                ['Moderate (20-35)', f"{self.stats.get('pct_moderate', 0):.1f}%"],
                ['Blurry Objects (<20)', f"{self.stats['pct_blurry']:.1f}%"],
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
                quality = "Needs Improvement"
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
        # SIZE CLASS BREAKDOWN
        # =====================================================================
        if sections.get('size_class_breakdown', True) and 'size_classes' in self.stats:
            story.append(Paragraph("Size Class Distribution", section_style))
            
            size_data = [['Size Class', 'Count', 'Percentage']]
            total = sum(self.stats['size_classes'].values())
            
            for label, count in self.stats['size_classes'].items():
                pct = (count / total * 100) if total > 0 else 0
                size_data.append([label, f"{count:,}", f"{pct:.1f}%"])
            
            size_table = Table(size_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            size_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#673AB7')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ]))
            story.append(size_table)
            story.append(Spacer(1, 20))
        
        # =====================================================================
        # VISUALIZATIONS
        # =====================================================================
        story.append(PageBreak())
        story.append(Paragraph("Visualizations", section_style))
        story.append(Spacer(1, 10))
        
        # Size distribution
        if sections.get('size_distribution', True):
            try:
                size_plot = self._create_size_distribution_plot()
                story.append(Paragraph("Size Distribution", body_style))
                story.append(ReportLabImage(size_plot, width=5.5*inch, height=2.75*inch))
                story.append(Spacer(1, 15))
            except Exception as e:
                story.append(Paragraph(f"[Size plot error: {e}]", body_style))
        
        # Spatial heatmap
        if sections.get('spatial_heatmap', True):
            try:
                heatmap_plot = self._create_heatmap_plot()
                story.append(Paragraph("Spatial Distribution", body_style))
                story.append(ReportLabImage(heatmap_plot, width=5.5*inch, height=3.5*inch))
                story.append(Spacer(1, 15))
            except Exception as e:
                story.append(Paragraph(f"[Heatmap error: {e}]", body_style))
        
        # Blur distribution
        if sections.get('blur_distribution', True) and 'object_blur_score' in self.df:
            try:
                blur_plot = self._create_blur_distribution_plot()
                if blur_plot:
                    story.append(PageBreak())
                    story.append(Paragraph("Focus Quality Distribution", body_style))
                    story.append(ReportLabImage(blur_plot, width=5.5*inch, height=2.75*inch))
                    story.append(Spacer(1, 15))
            except Exception as e:
                story.append(Paragraph(f"[Blur plot error: {e}]", body_style))
        
        # Temporal analysis
        if sections.get('temporal_analysis', True):
            try:
                temporal_plot = self._create_temporal_plot()
                if temporal_plot:
                    story.append(Paragraph("Objects Over Time", body_style))
                    story.append(ReportLabImage(temporal_plot, width=5.5*inch, height=2.75*inch))
                    story.append(Spacer(1, 15))
            except Exception as e:
                story.append(Paragraph(f"[Temporal plot error: {e}]", body_style))
        
        # Morphology scatter
        if sections.get('morphology_scatter', True):
            try:
                morph_plot = self._create_morphology_scatter()
                story.append(Paragraph("Morphology Space", body_style))
                story.append(ReportLabImage(morph_plot, width=5.5*inch, height=3.5*inch))
            except Exception as e:
                story.append(Paragraph(f"[Morphology plot error: {e}]", body_style))
        
        # =====================================================================
        # REPRESENTATIVE GALLERY
        # =====================================================================
        if sections.get('representative_gallery', True) and self.config['gallery']['enabled']:
            story.append(PageBreak())
            story.append(Paragraph("Representative Objects Gallery", section_style))
            
            gallery_cfg = self.config['gallery']
            story.append(Paragraph(
                f"Top {gallery_cfg['num_clusters']} most prevalent object groups, "
                f"clustered by {gallery_cfg['clustering_method']}, "
                f"selecting {'least blurry' if gallery_cfg['prefer_least_blurry'] else 'largest'} representative.",
                caption_style
            ))
            story.append(Spacer(1, 10))
            
            try:
                gallery_items = self._create_representative_gallery()
                
                if gallery_items:
                    # Create grid image
                    grid_image = self._create_gallery_grid_image(gallery_items)
                    if grid_image:
                        story.append(ReportLabImage(grid_image, width=6.5*inch, height=5*inch))
                        story.append(Spacer(1, 10))
                    
                    # Add stats table for top items
                    if gallery_cfg['show_cluster_stats']:
                        stats_header = ['#', 'Group %', 'Count', 'Size (µm)', 'Blur']
                        stats_rows = [stats_header]
                        
                        for i, item in enumerate(gallery_items[:10]):  # Top 10
                            s = item['stats']
                            stats_rows.append([
                                str(i + 1),
                                f"{s['pct_of_total']:.1f}%",
                                str(s['cluster_size']),
                                f"{s.get('esd_um', 0):.1f}" if 'esd_um' in s else 'N/A',
                                f"{s.get('blur_score', 0):.0f}" if 'blur_score' in s else 'N/A'
                            ])
                        
                        gallery_table = Table(stats_rows, colWidths=[0.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
                        gallery_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#607D8B')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 9),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                        ]))
                        story.append(gallery_table)
                else:
                    story.append(Paragraph("No representative images found.", body_style))
                    
            except Exception as e:
                story.append(Paragraph(f"[Gallery error: {e}]", body_style))
        
        # =====================================================================
        # FOOTER
        # =====================================================================
        if self.config['output']['include_footer']:
            story.append(Spacer(1, 30))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                "Generated by PlanktoScope Enhanced Report Generator v2.0",
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
        print("Usage: python3 sample_report_v2.py <tsv_path> [output_pdf] [config_json]")
        print("\nGenerates a customizable PDF report from segmentation TSV data.")
        print("\nOptions:")
        print("  --generate-config    Create a default configuration file")
        print("\nExample:")
        print("  python3 sample_report_v2.py ecotaxa_A_106.tsv")
        print("  python3 sample_report_v2.py ecotaxa_A_106.tsv report.pdf config.json")
        print("  python3 sample_report_v2.py --generate-config")
        sys.exit(1)
    
    if sys.argv[1] == '--generate-config':
        config_path = sys.argv[2] if len(sys.argv) > 2 else 'report_config.json'
        generate_default_config(config_path)
        sys.exit(0)
    
    tsv_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    config_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        generator = EnhancedReportGenerator(tsv_path, config=config_path)
        pdf_path = generator.generate_pdf(output_path)
        print(f"\n✓ Report saved to: {pdf_path}")
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
