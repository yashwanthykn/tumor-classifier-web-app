from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from app.database.models import Prediction

#creating objects i guess
def create_prediction(
    db: Session,
    user_id: int,
    filename: str,
    file_size: int,
    prediction_label: str,
    confidence_score: float,
    processing_time: float,
    model_version: str = "vgg16_v1"
) -> Prediction:
    """Create a new prediction record."""
    db_prediction = Prediction(
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        prediction_label=prediction_label,
        confidence_score=confidence_score,
        processing_time=processing_time,
        model_version=model_version
    )

    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)
    return db_prediction

def get_prediction_by_id(db: Session, prediction_id: int) -> Optional[Prediction]:
    """Get a prediction by ID."""
    return db.query(Prediction).filter(Prediction.id == prediction_id).first()

def get_all_predictions(db: Session, skip: int = 0, limit: int = 100) -> List[Prediction]:
    """Get all predictions with pagination."""
    return db.query(Prediction).offset(skip).limit(limit).all()

def get_user_predictions(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[Prediction]:
    """Get all predictions for a specific user."""
    return (
        db.query(Prediction)
        .filter(Prediction.user_id == user_id)
        .order_by(Prediction.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_recent_predictions(
    db: Session,
    days: int = 7,
    limit: int = 50
) -> List[Prediction]:
    """Get recent predictions within specified days."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(Prediction)
        .filter(Prediction.created_at >= cutoff_date)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

def get_statistics(db: Session, user_id: int) -> dict:
    """Get prediction statistics for a user."""
    total_predictions = (
        db.query(Prediction)
        .filter(Prediction.user_id == user_id)
        .count()
    )

    tumor_count = (
        db.query(Prediction)
        .filter(
            Prediction.user_id == user_id,
            Prediction.prediction_label == "Tumor"
        )
        .count()
    )

    avg_confidence = (
        db.query(func.avg(Prediction.confidence_score))
        .filter(Prediction.user_id == user_id)
        .scalar()
    )
    return {
        "total_predictions": total_predictions,
        "tumor_detected": tumor_count,
        "average_confidence": round(float(avg_confidence or 0), 4),
        "no_tumor_detected": total_predictions - tumor_count
    }

def delete_prediction(db: Session, prediction_id: int) -> bool:
    """Delete a prediction by ID."""
    db_prediction = get_prediction_by_id(db, prediction_id)
    if db_prediction:
        db.delete(db_prediction)
        db.commit()
        return True
    return False
