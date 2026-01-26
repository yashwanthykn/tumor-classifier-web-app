#database operations
# what is crud? > create read update delete 
#*********
# create-Insert, read-select, update-update,delete-delete
#*************
from sqlalchemy.orm import Session
# Session Type hint for individual database connections 
# just says "this is a database session type"
#sessionmaker creates sessions using the Session class internally

from sqlalchemy import func
#lets you call databae functions from python code

from typing import List,Optional
#for type hinting Optional-this can be None

from datetime import datetime, timedelta,timezone

from app.database.models import Prediction

#save a new preditions to database when model makes a new predictions
def create_prediction(db:Session,
                      user_id:int,
                      filename:str,
                      file_size:int,
                      prediction_label: str,
                      confidence_score: float,
                      processing_time: float,
                      model_version: str = "vgg16_v1")->Prediction:
     
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
     #starts tracking the object
     db.commit()
     """Session sees pending objects
        Converts Python object → SQL
        Session asks engine for a connection
        Engine:
          Opens or reuses a PostgreSQL connection
        SQL is executed
        PostgreSQL:
          Saves the row
          Generates:
               id
               created_at"""
               
     #those generated values are not automatically updated in the db_prediction until we refresh the object
     db.refresh(db_prediction)
     return db_prediction

def get_prediction_by_id(db: Session, prediction_id: int) -> Optional[Prediction]:
    return db.query(Prediction).filter(Prediction.id == prediction_id).first()
  
def get_all_predictions(db:Session,skip:int=0,limit:int=100)->List[Prediction]:
    return db.query(Prediction).offset(skip).limit(limit).all()

def get_user_predictions(db:Session,user_id:int,skip:int=0,limit:int=100)->List[Prediction]:
    return db.query(Prediction).filter(Prediction.user_id==user_id).offset(skip).limit(limit).order_by(Prediction.created_at.desc()).all()
##****************
# .all() .first() is an ORM execution method 
# Executes the query and returns all the result
##****************
def get_recent_predictions(db:Session,days:int=7,limit:int=50)->List[Prediction]:
    cutoff_date=datetime.now(timezone.utc)-timedelta(days=days)
    return (
      db.query(Prediction).filter(Prediction.created_at>=cutoff_date).order_by(Prediction.created_at.desc()).limit(limit).all()
    )
    
#aggregation queries
def get_statistics(db:Session,user_id:int)->dict:
    total_predictions = db.query(Prediction).filter(Prediction.user_id==user_id).count()
    
    tumor_count = db.query(Prediction).filter(Prediction.user_id==user_id, Prediction.prediction_label == "Tumor"
    ).count()
    
    avg_confidence = db.query(func.avg(Prediction.confidence_score)).filter(Prediction.user_id==user_id).scalar()
    
    return{
      "total_predictions": total_predictions,
      "tumor_detected": tumor_count,  # FIXED: Changed key name to match frontend expectation
      "average_confidence": round(float(avg_confidence or 0),4),
      "no_tumor_detected": total_predictions - tumor_count  # FIXED: Changed key name to match frontend
    }
    
def delete_prediction(db:Session,prediction_id:int)->bool:
    db_prediction=get_prediction_by_id(db,prediction_id)
    """db_prediction=db.query(Prediction).filter(Prediction.id==prediction_id).first()"""
    if db_prediction:
          db.delete(db_prediction)
          db.commit()
          return True
    return False
