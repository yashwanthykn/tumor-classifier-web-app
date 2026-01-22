from PIL import Image
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.applications.vgg16 import preprocess_input

def Pre_processing_image(image_path:str,target_size=(224,224)):
     
     try:
        img = Image.open(image_path).convert("RGB")
     except Exception as e:
        raise ValueError(f"Error loading image: {e}")
   
     img=img.resize(target_size)
     
     # PIl to Numpy array
     
     img_array=np.array(img,dtype=np.float32)
     
     img_array=preprocess_input(img_array)
     
     img_array=np.expand_dims(img_array,axis=0)
     
     return img_array