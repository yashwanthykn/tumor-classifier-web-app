import tensorflow as tf
import logging
import os

logging.basicConfig(level=logging.INFO)


class ModelLoader:
    """Load and manage the TensorFlow model."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None

    def load(self):
        """Load the model from disk."""
        if not os.path.exists(self.model_path):
            logging.error(f"Model file not found: {self.model_path}")
            raise FileNotFoundError(f"{self.model_path} does not exist")

        try:
            self.model = tf.keras.models.load_model(self.model_path, compile=False)
            logging.info(f"Model loaded successfully from path {self.model_path}")
        except Exception as e:
            logging.exception(f"Error loading model: {e}")
            raise e

        return self.model