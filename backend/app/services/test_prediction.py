import logging
from predictor import Predictor
import os

logging.basicConfig(level=logging.INFO)

model_path=r"C:\Things\KOBE\Merage5\tumor-classifier\model\tumor_model.keras"
image_path=r"C:\Things\KOBE\Merage5\tumor-classifier\test_image\N1.jpg"


"""
print("Model exists:", os.path.exists(model_path))
print("Image exists:", os.path.exists(image_path))
"""

def main():
     
     logging.info('Initializing Predictor')
     
     predictor=Predictor(model_path)
     
     logging.info("Running Prediction on test image")
     
     result=predictor.predict_img(image_path)
     
     print("\n========== PREDICTION RESULT ==========")
     print(f"Label:       {result.get('label')}")
     print(f"Confidence:  {result.get('confidence')}")
     print("========================================\n")


if __name__ == "__main__":
    main()


