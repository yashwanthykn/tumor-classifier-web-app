import logging 
from app.services.model_loader import ModelLoader
from app.services.preprocessing import Pre_processing_image


class Predictor:
     def __init__(self,model_path:str):
          self.model_loader=ModelLoader(model_path)
          self.model=self.model_loader.load()
          
     
     def predict_img(self,image_path:str)->dict:
          
          try:
               img_array=Pre_processing_image(image_path)
               
               preds=self.model.predict(img_array)
               
               confidence=float(preds[0][0])
               label="Tumor" if confidence>=0.5 else "Not A Tumor"
               
               logging.info(f"Prediction : {label} ({confidence:.4f} for {image_path})")
               
               return {"label": label,"confidence":confidence}
          
          except Exception as e :
               logging.exception(f"Prediction failed for {image_path}:{e}")
               
               return {"label":None,"confidence":0.0}