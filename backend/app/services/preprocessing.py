from PIL import Image
import numpy as np
from tensorflow.keras.applications.vgg16 import preprocess_input


def Pre_processing_image(image_path: str, target_size=(224, 224)):
    """Preprocess image for VGG16 model with validation."""
    
    warnings = {
        "is_color_image": False,
        "low_contrast": False
    }
    
    try:
        img = Image.open(image_path)
        original_mode = img.mode
        
        # Check if image is "too colorful" to be an MRI
        if original_mode in ("RGB", "RGBA"):
            warnings["is_color_image"] = _is_color_photo(img)
        
        # Convert to RGB for VGG16
        img = img.convert("RGB")
        
    except Exception as e:
        raise ValueError(f"Error loading image: {e}")

    img = img.resize(target_size)

    # PIL to Numpy array
    img_array = np.array(img, dtype=np.float32)
    
    # Check contrast
    if img_array.std() < 20:
        warnings["low_contrast"] = True

    # Apply VGG16 preprocessing
    img_array = preprocess_input(img_array)

    # Add batch dimension
    img_array = np.expand_dims(img_array, axis=0)

    return img_array, warnings


def _is_color_photo(img: Image.Image, threshold: float = 15.0) -> bool:
    """
    Detect if an image is a color photograph vs grayscale medical scan.
    
    MRI/CT scans are grayscale, so R ≈ G ≈ B for every pixel.
    Color photos have significant differences between channels.
    """
    rgb_array = np.array(img.convert("RGB"), dtype=np.float32)
    
    r = rgb_array[:, :, 0]
    g = rgb_array[:, :, 1]
    b = rgb_array[:, :, 2]
    
    # Calculate color variance across channels
    # For grayscale images, this should be near 0
    channel_means = [r.mean(), g.mean(), b.mean()]
    color_variance = np.std(channel_means)
    
    # Also check per-pixel color difference
    rg_diff = np.abs(r - g).mean()
    rb_diff = np.abs(r - b).mean()
    gb_diff = np.abs(g - b).mean()
    avg_channel_diff = (rg_diff + rb_diff + gb_diff) / 3
    
    # If channels differ significantly, it's a color image
    is_color = color_variance > threshold or avg_channel_diff > threshold
    
    return is_color