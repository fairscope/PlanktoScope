#!/usr/bin/env python3
"""
PlanktoScope Hierarchical Classifier v5 - PRODUCTION VERSION

Fast envelope-first segmentation optimized for large images.

Key optimizations:
- ROI-based processing: only analyze the bounding region of each object
- Skip watershed for clearly single objects (high solidity)
- Batch distance transform on full image, then extract per-contour
- Smart size-based skipping
"""

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np


class PlanktoScopeHierarchicalClassifier:
    
    def __init__(self):
        self.last_segmentation = None
        self.last_image_path = None
        self.last_params = None
        self.last_debug_info = {}
    
    def segment_and_extract(self, image_path: str, params: dict) -> dict:
        """Main entry point."""
        start_time = time.time()
        
        img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "error": f"Could not load {image_path}"}
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        
        self.last_image_path = image_path
        self.last_params = params
        
        # Run optimized segmentation
        objects, envelope_mask, debug_info = self._segment_optimized(gray, params)
        
        # Format output
        pixel_size = float(params.get("pixel_size", 0.94))
        expand_factor = float(params.get("expand_bbox_factor", 0.1))
        H, W = gray.shape[:2]
        
        formatted_objects = []
        for i, obj in enumerate(objects):
            bbox = obj["bbox"]
            x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
            
            if expand_factor > 0:
                x_exp = int(w * expand_factor / 2)
                y_exp = int(h * expand_factor / 2)
                x = max(0, x - x_exp)
                y = max(0, y - y_exp)
                w = min(W - x, w + 2 * x_exp)
                h = min(H - y, h + 2 * y_exp)
            
            formatted_objects.append({
                "id": i + 1,
                "bbox": {"x": x, "y": y, "width": w, "height": h},
                "diameter_um": obj["diameter_um"],
                "area_px": obj.get("area_px", 0),
                "method": obj.get("method", "envelope"),
            })
        
        process_time = time.time() - start_time
        
        self.last_debug_info = debug_info
        self.last_segmentation = {
            "objects": formatted_objects,
            "mask": envelope_mask,
            "image": img,
            "crops": self._extract_crops(img, formatted_objects)
        }
        
        return {
            "status": "success",
            "objects": formatted_objects,
            "objects_found": len(formatted_objects),
            "method_used": "hierarchical_v5",
            "overlap_score": 0.0,
            "processing_time": process_time,
            "debug": debug_info
        }
    
    def process_image_path(self, image_path: str, params: dict) -> dict:
        return self.segment_and_extract(image_path, params)
    
    def save_objects(self, output_base_dir: str = None) -> dict:
        if self.last_segmentation is None:
            return {"status": "error", "error": "No segmentation results"}
        
        output_dir = Path(output_base_dir or "/home/pi/data/segmented")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        crops = self.last_segmentation.get("crops", [])
        saved_count = 0
        
        for i, crop in enumerate(crops):
            if crop is not None and crop.size > 0:
                cv2.imwrite(str(output_dir / f"object_{i+1:04d}.jpg"), crop)
                saved_count += 1
        
        return {"status": "success", "saved_count": saved_count}
    
    def _extract_crops(self, img: np.ndarray, objects: list) -> list:
        crops = []
        for obj in objects:
            bbox = obj["bbox"]
            x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
            y1, y2 = max(0, y), min(img.shape[0], y + h)
            x1, x2 = max(0, x), min(img.shape[1], x + w)
            crops.append(img[y1:y2, x1:x2].copy() if x2 > x1 and y2 > y1 else None)
        return crops
    
    def _segment_optimized(self, gray: np.ndarray, params: dict) -> tuple:
        """Optimized segmentation with ROI-based watershed."""
        min_diameter = float(params.get("min_diameter", 30))
        pixel_size = float(params.get("pixel_size", 0.94))
        min_radius_px = min_diameter / (2 * pixel_size)
        min_area_px = np.pi * min_radius_px ** 2
        
        # Maximum area filter - reject objects larger than this ratio of frame
        max_area_ratio = float(params.get("max_area_ratio", 0.25))
        H, W = gray.shape[:2]
        max_area_px = H * W * max_area_ratio
        
        # Only consider splitting objects larger than 4x minimum
        split_min_area = min_area_px * 4
        
        debug_info = {
            "envelopes_found": 0,
            "envelopes_kept": 0,
            "envelopes_split": 0,
            "skipped_small": 0
        }
        
        # Preprocess
        processed = gray.copy()
        if params.get("use_clahe", False):
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            processed = clahe.apply(processed)
        
        # Find envelopes
        blurred = cv2.GaussianBlur(processed, (5, 5), 0)
        
        threshold_method = params.get("threshold_method", "otsu")
        if threshold_method == "adaptive":
            block_size = int((min_diameter / pixel_size) * 1.5)
            block_size = max(3, block_size | 1)
            binary = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, block_size, 5
            )
        else:
            _, binary = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
        
        # Morphology
        close_size = min(7, max(3, int((min_diameter / pixel_size) * 0.15)) | 1)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
        envelopes = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel, iterations=2)
        
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        envelopes = cv2.morphologyEx(envelopes, cv2.MORPH_OPEN, open_kernel, iterations=1)
        
        # Find and fill contours
        contours, _ = cv2.findContours(envelopes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(envelopes)
        cv2.drawContours(filled, contours, -1, 255, -1)
        
        debug_info["envelopes_found"] = len(contours)
        
        # Process each contour
        final_objects = []
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area_px:
                continue
            
            # Skip objects that are too large (likely background/frame detection)
            if area > max_area_px:
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            diameter_um = 2 * np.sqrt(area / np.pi) * pixel_size
            
            # Small objects: skip split analysis
            if area < split_min_area:
                debug_info["skipped_small"] += 1
                final_objects.append({
                    "contour": cnt,
                    "bbox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                    "area_px": area,
                    "diameter_um": diameter_um,
                    "split": False,
                    "method": "envelope"
                })
                continue
            
            # Quick solidity check
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 1.0
            
            # High solidity = definitely single
            if solidity > 0.85:
                debug_info["envelopes_kept"] += 1
                final_objects.append({
                    "contour": cnt,
                    "bbox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                    "area_px": area,
                    "diameter_um": diameter_um,
                    "split": False,
                    "method": "envelope"
                })
                continue
            
            # ROI-based split analysis (FAST!)
            should_split, sub_objects = self._analyze_and_split_roi(
                gray, filled, cnt, x, y, w, h, solidity, params
            )
            
            if should_split and len(sub_objects) >= 2:
                debug_info["envelopes_split"] += 1
                final_objects.extend(sub_objects)
            else:
                debug_info["envelopes_kept"] += 1
                final_objects.append({
                    "contour": cnt,
                    "bbox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                    "area_px": area,
                    "diameter_um": diameter_um,
                    "split": False,
                    "method": "envelope"
                })
        
        return final_objects, filled, debug_info
    
    def _analyze_and_split_roi(self, gray: np.ndarray, filled: np.ndarray,
                                cnt: np.ndarray, x: int, y: int, w: int, h: int,
                                solidity: float, params: dict) -> tuple:
        """
        Analyze and potentially split a contour using ROI-based processing.
        
        This is MUCH faster than full-image processing because we only
        work on the small bounding region of the object.
        """
        min_diameter = float(params.get("min_diameter", 30))
        pixel_size = float(params.get("pixel_size", 0.94))
        min_area_px = np.pi * (min_diameter / (2 * pixel_size)) ** 2
        
        # Add padding to ROI
        pad = 10
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(gray.shape[1], x + w + pad)
        y2 = min(gray.shape[0], y + h + pad)
        
        # Extract ROI
        roi_mask = filled[y1:y2, x1:x2].copy()
        roi_gray = gray[y1:y2, x1:x2]
        
        # Create contour mask in ROI coordinates
        shifted_cnt = cnt - [x1, y1]
        cnt_mask = np.zeros_like(roi_mask)
        cv2.drawContours(cnt_mask, [shifted_cnt], -1, 255, -1)
        
        # Distance transform on small ROI (FAST!)
        dist = cv2.distanceTransform(cnt_mask, cv2.DIST_L2, 5)
        max_dist = dist.max()
        
        if max_dist < 3:
            return False, []
        
        # Find peaks
        kernel_size = max(5, int((min_diameter / pixel_size) * 0.2)) | 1
        dilated = cv2.dilate(dist, np.ones((kernel_size, kernel_size)))
        peaks = (dist == dilated) & (dist > max_dist * 0.35)
        num_peaks = cv2.countNonZero(peaks.astype(np.uint8))
        
        # Decision: split if multiple peaks and low solidity
        should_split = (num_peaks >= 2 and solidity < 0.78)
        
        # Also check aspect ratio
        if not should_split:
            aspect = max(w, h) / max(min(w, h), 1)
            if aspect > 2.5 and solidity < 0.72:
                should_split = True
        
        if not should_split:
            return False, []
        
        # Watershed on ROI (FAST!)
        dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        _, sure_fg = cv2.threshold(dist_norm, 0.35 * dist_norm.max(), 255, 0)
        sure_fg = sure_fg.astype(np.uint8)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        sure_bg = cv2.dilate(cnt_mask, kernel, iterations=2)
        unknown = cv2.subtract(sure_bg, sure_fg)
        
        num_labels, markers = cv2.connectedComponents(sure_fg)
        markers = markers + 1
        markers[unknown == 255] = 0
        
        roi_color = cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
        markers = cv2.watershed(roi_color, markers)
        
        # Extract sub-objects
        sub_objects = []
        for label_id in range(2, num_labels + 2):
            label_mask = (markers == label_id).astype(np.uint8) * 255
            
            if cv2.countNonZero(label_mask) < min_area_px * 0.25:
                continue
            
            # Check overlap with original contour
            overlap = cv2.bitwise_and(label_mask, cnt_mask)
            if cv2.countNonZero(overlap) < cv2.countNonZero(label_mask) * 0.6:
                continue
            
            sub_contours, _ = cv2.findContours(label_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not sub_contours:
                continue
            
            sub_cnt = max(sub_contours, key=cv2.contourArea)
            sub_area = cv2.contourArea(sub_cnt)
            if sub_area < min_area_px * 0.25:
                continue
            
            # Convert back to full image coordinates
            sub_cnt_full = sub_cnt + [x1, y1]
            sx, sy, sw, sh = cv2.boundingRect(sub_cnt_full)
            sub_diameter = 2 * np.sqrt(sub_area / np.pi) * pixel_size
            
            sub_objects.append({
                "contour": sub_cnt_full,
                "bbox": {"x": int(sx), "y": int(sy), "width": int(sw), "height": int(sh)},
                "area_px": sub_area,
                "diameter_um": sub_diameter,
                "split": True,
                "method": "watershed"
            })
        
        return len(sub_objects) >= 2, sub_objects


# Default instance
classifier = PlanktoScopeHierarchicalClassifier()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <image> [min_diameter]")
        sys.exit(1)
    
    image_path = sys.argv[1]
    min_diam = float(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    params = {
        "min_diameter": min_diam,
        "pixel_size": 0.94,
        "threshold_method": "otsu",
        "expand_bbox_factor": 0.1
    }
    
    result = classifier.segment_and_extract(image_path, params)
    
    print(f"Objects: {result.get('objects_found', 0)}")
    print(f"Time: {result.get('processing_time', 0)*1000:.0f}ms")
    
    if result.get("debug"):
        d = result["debug"]
        print(f"Envelopes: {d['envelopes_found']}, kept: {d['envelopes_kept']}, "
              f"split: {d['envelopes_split']}, skipped: {d.get('skipped_small', 0)}")
