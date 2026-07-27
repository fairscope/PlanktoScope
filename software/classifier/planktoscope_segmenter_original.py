#!/usr/bin/env python3
"""
planktoscope_segmenter_original.py - Original PlanktoScope Segmentation Method

This implements the original PlanktoScope segmentation pipeline:
- Adaptive threshold (blocksize=19, C=4)
- Erode (2x2 rect kernel)
- Dilate (8x8 ellipse kernel)  
- Close (8x8 ellipse kernel)
- Erode2 (8x8 ellipse kernel)
- Find contours and extract ROIs

This matches the segmenter from the most recent version:
https://github.com/PlanktoScope/PlanktoScope/tree/main/segmenter

Copyright follows the original PlanktoScope GPL v3 license.
"""

import cv2
import numpy as np
import json
import os
import time
from pathlib import Path


try:
    from loguru import logger
except ImportError:
    class SimpleLogger:
        def debug(self, msg): pass
        def info(self, msg): print(f"INFO: {msg}")
        def success(self, msg): print(f"SUCCESS: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
    logger = SimpleLogger()


class PlanktoScopeOriginalSegmenter:
    """Original PlanktoScope segmentation pipeline."""
    
    def __init__(self):
        self.previous_mask = None
    
    def reset(self):
        """Reset the previous mask for a new acquisition."""
        self.previous_mask = None
    
    def adaptative_threshold(self, img):
        """Apply adaptive threshold to get binary mask.
        
        Uses ADAPTIVE_THRESH_MEAN_C with blockSize=19, C=4
        """
        logger.debug("Adaptive threshold calc")
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = cv2.adaptiveThreshold(
            img_gray,
            maxValue=255,
            adaptiveMethod=cv2.ADAPTIVE_THRESH_MEAN_C,
            thresholdType=cv2.THRESH_BINARY_INV,
            blockSize=19,
            C=4,
        )
        logger.success("Adaptive threshold done")
        return mask
    
    def simple_threshold(self, img):
        """Apply simple threshold using triangle method."""
        logger.debug("Simple threshold calc")
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, mask = cv2.threshold(
            img_gray, 127, 255, 
            cv2.THRESH_BINARY_INV + cv2.THRESH_TRIANGLE
        )
        logger.info(f"Threshold value used: {ret}")
        return mask
    
    def erode(self, mask):
        """Erode with 2x2 rectangular kernel."""
        logger.debug("Erode calc")
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        return cv2.erode(mask, kernel)
    
    def dilate(self, mask):
        """Dilate with 8x8 elliptical kernel."""
        logger.debug("Dilate calc")
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        return cv2.dilate(mask, kernel)
    
    def close(self, mask):
        """Close operation with 8x8 elliptical kernel."""
        logger.debug("Close calc")
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    def erode2(self, mask):
        """Second erode with 8x8 elliptical kernel."""
        logger.debug("Erode2 calc")
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        return cv2.erode(mask, kernel)
    
    def remove_previous_mask(self, mask):
        """Remove objects from previous frame (for stuck particles)."""
        if self.previous_mask is not None:
            mask_and = mask & self.previous_mask
            mask_final = mask - mask_and
            logger.debug("Removed previous mask")
            self.previous_mask = mask.copy()
            return mask_final
        else:
            logger.debug("First mask, no previous to remove")
            self.previous_mask = mask.copy()
            return mask
    
    def extract_features(self, img, mask, bbox, label):
        """Extract scikit-image style features from a region.
        
        This mimics the feature extraction from the original PlanktoScope.
        """
        x, y, w, h = bbox
        
        # Extract the ROI from mask
        roi_mask = mask[y:y+h, x:x+w]
        roi_img = img[y:y+h, x:x+w]
        
        # Calculate basic properties
        area = np.sum(roi_mask > 0)
        if area == 0:
            return None
        
        # Contour for perimeter
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None
        
        cnt = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(cnt, True)
        
        # Moments for centroid
        M = cv2.moments(roi_mask)
        if M["m00"] == 0:
            return None
        
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        
        # Fit ellipse for major/minor axes
        if len(cnt) >= 5:
            ellipse = cv2.fitEllipse(cnt)
            (ex, ey), (minor, major), angle = ellipse
        else:
            major = max(w, h)
            minor = min(w, h)
            angle = 0
        
        # Convex hull
        hull = cv2.convexHull(cnt)
        convex_area = cv2.contourArea(hull)
        
        # Circularity
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
        else:
            circularity = 0
        
        # Solidity
        if convex_area > 0:
            solidity = area / convex_area
        else:
            solidity = 0
        
        # Elongation
        if minor > 0:
            elongation = major / minor
        else:
            elongation = 1
        
        # Equivalent diameter
        equivalent_diameter = np.sqrt(4 * area / np.pi)
        
        # Eccentricity (approximation)
        if major > 0:
            eccentricity = np.sqrt(1 - (minor/major)**2) if major > minor else 0
        else:
            eccentricity = 0
        
        # HSV statistics
        roi_hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        mask_bool = roi_mask > 0
        
        if np.any(mask_bool):
            h_vals = roi_hsv[:,:,0][mask_bool]
            s_vals = roi_hsv[:,:,1][mask_bool]
            v_vals = roi_hsv[:,:,2][mask_bool]
            
            mean_hue = np.mean(h_vals)
            mean_sat = np.mean(s_vals)
            mean_val = np.mean(v_vals)
            std_hue = np.std(h_vals)
            std_sat = np.std(s_vals)
            std_val = np.std(v_vals)
        else:
            mean_hue = mean_sat = mean_val = 0
            std_hue = std_sat = std_val = 0
        
        # Calculate area with holes excluded
        area_exc = area  # Simplified - would need more complex logic for holes
        
        features = {
            "label": label,
            "width": w,
            "height": h,
            "bx": x,
            "by": y,
            "circ.": circularity,
            "area_exc": int(area_exc),
            "area": int(area),
            "%area": 0 if area == 0 else (area - area_exc) / area,
            "major": major,
            "minor": minor,
            "y": y + cy,
            "x": x + cx,
            "convex_area": int(convex_area),
            "perim.": perimeter,
            "elongation": elongation,
            "perimareaexc": perimeter / area_exc if area_exc > 0 else 0,
            "perimmajor": perimeter / major if major > 0 else 0,
            "circex": circularity,
            "angle": angle,
            "bounding_box_area": w * h,
            "eccentricity": eccentricity,
            "equivalent_diameter": equivalent_diameter,
            "euler_number": 0,  # Simplified
            "extent": area / (w * h) if w * h > 0 else 0,
            "local_centroid_col": cx,
            "local_centroid_row": cy,
            "solidity": solidity,
            "MeanHue": mean_hue,
            "MeanSaturation": mean_sat,
            "MeanValue": mean_val,
            "StdHue": std_hue,
            "StdSaturation": std_sat,
            "StdValue": std_val,
        }
        
        return features
    
    def segment_and_extract(self, image_path, params=None):
        """Run the full PlanktoScope segmentation pipeline.
        
        Args:
            image_path: Path to input image
            params: Optional parameters dict with:
                - min_diameter: Minimum object diameter in µm (default 20)
                - pixel_size: µm per pixel (default 0.94)
                - threshold_method: 'adaptive' or 'simple' (default 'adaptive')
                - remove_previous: Whether to subtract previous mask (default False)
        
        Returns:
            dict with status, objects list, timing info
        """
        if params is None:
            params = {}
        
        min_diameter = params.get("min_diameter", 20)
        pixel_size = params.get("pixel_size", 0.94)
        threshold_method = params.get("threshold_method", "adaptive")
        remove_previous = params.get("remove_previous", False)
        
        # Calculate minimum area in pixels
        min_area_px = int((min_diameter / pixel_size / 2) ** 2 * np.pi)
        
        # Maximum area filter - reject full-frame detections
        max_area_ratio = params.get("max_area_ratio", 0.25)
        
        start_time = time.time()
        
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "error": f"Could not load image: {image_path}"}
        
        # Calculate max area based on image size
        max_area_px = img.shape[0] * img.shape[1] * max_area_ratio
        
        # Step 1: Threshold
        if threshold_method == "simple":
            mask = self.simple_threshold(img)
        else:
            mask = self.adaptative_threshold(img)
        
        # Step 2: Morphological operations (PlanktoScope pipeline)
        mask = self.erode(mask)
        mask = self.dilate(mask)
        mask = self.close(mask)
        mask = self.erode2(mask)
        
        # Step 3: Optionally remove previous mask
        if remove_previous:
            mask = self.remove_previous_mask(mask)
        
        # Step 4: Find contours
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # Step 5: Extract objects
        objects = []
        obj_id = 0
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area_px:
                continue
            
            # Skip objects that are too large (likely full-frame detection)
            if area > max_area_px:
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Skip edge objects
            if x <= 1 or y <= 1:
                continue
            if x + w >= img.shape[1] - 1 or y + h >= img.shape[0] - 1:
                continue
            
            obj_id += 1
            
            # Extract features
            features = self.extract_features(img, mask, (x, y, w, h), obj_id)
            if features is None:
                continue
            
            # Calculate diameter
            diameter_um = features["equivalent_diameter"] * pixel_size
            
            obj = {
                "id": obj_id,
                "bbox": {"x": x, "y": y, "width": w, "height": h},
                "diameter_um": diameter_um,
                "area_px": area,
                "features": features,
                "method": "planktoscope"
            }
            objects.append(obj)
        
        process_time = int((time.time() - start_time) * 1000)
        
        return {
            "status": "success",
            "objects": objects,
            "objects_found": len(objects),
            "processing_time_ms": process_time,
            "method": "planktoscope",
            "mask_shape": mask.shape
        }
    
    def segment_image_for_preview(self, image_path, params=None):
        """Segment and return visualization for preview."""
        result = self.segment_and_extract(image_path, params)
        
        if result["status"] != "success":
            return result
        
        # Load image for visualization
        img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "error": "Could not load image for preview"}
        
        # Draw bounding boxes
        for obj in result["objects"]:
            bbox = obj["bbox"]
            x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            # Add label
            label = f"#{obj['id']} ({int(obj['diameter_um'])}µm)"
            cv2.putText(img, label, (x, y-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        
        result["preview_image"] = img
        return result


# Singleton instance for use in segment_live.py
segmenter = PlanktoScopeOriginalSegmenter()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python planktoscope_segmenter_original.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    params = {
        "min_diameter": 20,
        "pixel_size": 0.94,
        "threshold_method": "adaptive"
    }
    
    result = segmenter.segment_and_extract(image_path, params)
    print(json.dumps(result, indent=2, default=str))
