from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Request
from sqlalchemy.orm import Session

from uuid import uuid4
import os
import shutil
import logging
import time


from app.utils.file_validator import validate_image_file, sanitize_filename
from app.api.Pydantic_Schema import PredictionResponse
from app.services.predictor import Predictor
from app.database.database import get_db
from app.crud import prediction as crud_prediction
from app.auth.dependencies import get_current_active_user
from app.database.models import User
from app.middleware.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("MODEL_PATH", "model/tumor_model.keras")
UPLOAD_DIR = os.path.join("backend", "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)
predictor = Predictor(MODEL_PATH)


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit("10/minute")
async def predict_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload an image and get tumor prediction."""
    
    # Validate uploaded file
    file_bytes = await validate_image_file(file)
    
    # Sanitize filename
    safe_filename = sanitize_filename(file.filename)
    unique_filename = f"{uuid4().hex}_{safe_filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    start_time = time.time()

    try:
        # Get file size
        file_size = len(file_bytes)
        #logger.info(file_size)
        # Save file temporarily
        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)

        logger.info("Saved file: %s", file_path)

        # Run prediction
        result = predictor.predict_img(file_path)
        processing_time = time.time() - start_time

        logger.info(
            "Prediction => label=%s confidence=%.4f",
            result["label"], result["confidence"]
        )

        # Save prediction to database
        db_prediction = crud_prediction.create_prediction(
            db=db,
            user_id=current_user.id,
            filename=safe_filename,
            file_size=file_size,
            prediction_label=result['label'],
            confidence_score=result['confidence'],
            processing_time=processing_time,
        )
        logger.info(f"Saved prediction to db with id: {db_prediction.id}")

        return PredictionResponse(**result)

    except Exception as e:
        logger.exception("Unexpected server error")
        raise HTTPException(500, "Internal server error.") from e

    finally:
        # Cleanup temp file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("Deleted temp file: %s", file_path)
            except Exception:
                logger.exception("Failed to delete temp file")


@router.get("/predictions")
@limiter.limit("30/minute")
async def get_predictions(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get prediction history for current user."""
    
    if skip < 0:
        raise HTTPException(status_code=400, detail="Skip must be >= 0")

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    predictions = crud_prediction.get_user_predictions(
        db,  user_id=current_user.id, skip=skip, limit=limit
    )
    return {"predictions": predictions, "total": len(predictions)}


@router.get("/predictions/{prediction_id}")
async def get_prediction(
    prediction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific prediction by ID."""
    
    prediction = crud_prediction.get_prediction_by_id(db, prediction_id)

    if not prediction:
        raise HTTPException(status_code=404, detail='Prediction not found')

    if prediction.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this prediction")

    return prediction


@router.get("/statistics")
@limiter.limit("20/minute")
async def get_statistics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get prediction statistics for current user."""
    stats = crud_prediction.get_statistics(db, user_id=current_user.id)
    return stats

