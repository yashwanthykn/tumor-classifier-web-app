import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model

import logging
import os

logging.basicConfig(level=logging.INFO)

class ModelLoader:
     
     def __init__(self,model_path:str):
          self.model_path=model_path
          self.model=None

     def load(self):
          if not os.path.exists(self.model_path):
               logging.error(f"Model file not found:{self.model_path}")
               raise FileNotFoundError(f"{self.model_path} does not exist")
          
          try:
               self.model=load_model(self.model_path)
               logging.info(f"Model loaded Successfully from path {self.model_path}")
          except Exception as e:
               logging.exception(f"Error loading Model : {e}")
               raise e
          
          return self.model