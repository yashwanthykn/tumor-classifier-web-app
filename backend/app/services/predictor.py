import logging
import numpy as np
from app.services.model_loader import ModelLoader
from app.services.preprocessing import Pre_processing_image


class Predictor:
    """Handle tumor predictions using the loaded model."""

    # Confidence thresholds
    PREDICTION_THRESHOLD = 0.5
    UNCERTAINTY_LOW = 0.35
    UNCERTAINTY_HIGH = 0.65
    
    def __init__(self, model_path: str):
        self.model_loader = ModelLoader(model_path)
        self.model = self.model_loader.load()

    def predict_img(self, image_path: str) -> dict:
        """Make a prediction on an image."""
        
        try:
            # Preprocess and validate
            img_array, validation_warnings = Pre_processing_image(image_path)
            
            # If image failed validation (e.g., too colorful), reject it
            if validation_warnings.get("is_color_image"):
                return {
                    "label": "Invalid Input",
                    "confidence": 0.0,
                    "message": "Please upload a grayscale MRI/CT scan, not a color photograph",
                    "valid_scan": False
                }
            
            # Run prediction
            preds = self.model.predict(img_array, verbose=0)
            confidence = float(preds[0][0])
            
            # Check if model is uncertain (prediction near 0.5)
            if self.UNCERTAINTY_LOW < confidence < self.UNCERTAINTY_HIGH:
                return {
                    "label": "Uncertain",
                    "confidence": round(confidence, 4),
                    "message": "Model is uncertain - image may not be a valid MRI scan",
                    "valid_scan": False
                }
            
            # Confident prediction
            if confidence >= self.PREDICTION_THRESHOLD:
                label = "Tumor"
                final_confidence = confidence
            else:
                label = "No Tumor"
                final_confidence = 1 - confidence  # Flip for "No Tumor" confidence
            
            logging.info(f"Prediction: {label} ({final_confidence:.4f}) for {image_path}")

            return {
                "label": label,
                "confidence": round(final_confidence, 4),
                "valid_scan": True
            }

        except Exception as e:
            logging.exception(f"Prediction failed for {image_path}: {e}")
            return {
                "label": "Error",
                "confidence": 0.0,
                "message": str(e),
                "valid_scan": False
            }