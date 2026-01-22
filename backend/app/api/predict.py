from fastapi import APIRouter, UploadFile, File, HTTPException, status,Depends
from fastapi import Request
from app.api.Pydantic_Schema import PredictionResponse
from uuid import uuid4
from PIL import Image
import os, shutil, logging

from app.services.predictor import Predictor

from sqlalchemy.orm import Session
from app.database.database import get_db
from app.crud import prediction as crud_prediction

from app.auth.dependencies import get_current_active_user
from app.database.models import User
import time


from app.utils.file_validator import validate_image_file, sanitize_filename
from app.middleware.rate_limit import limiter


router = APIRouter()
logger = logging.getLogger(__name__)

#MODEL_PATH = r"C:\Things\KOBE\Merage5\tumor-classifier\model\tumor_model.keras"

MODEL_PATH=os.getenv("MODEL_PATH","model/tumor_model.keras")
UPLOAD_DIR = os.path.join("backend","uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)
predictor = Predictor(MODEL_PATH)


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit("10/minute")
async def predict_image(request: Request,file: UploadFile = File(...),
                        db:Session = Depends(get_db),current_user:User=Depends(get_current_active_user)):
    #UploadFile tiny images into 10kb uses RAM and for large uploads uses harddrive
    #File(...) try to access the body of the files formData and required ...
    
    # 🆕 Step 1: Validate uploaded file
    await validate_image_file(file)
    
    # 🆕 Step 2: Sanitize filename
    safe_filename = sanitize_filename(file.filename)
    
    unique_filename = f"{uuid4().hex}_{safe_filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    #tracking processing time
    start_time=time.time()
    #records current time stamps
    
    try:
        #getting File size
        file.file.seek(0,os.SEEK_END)#this move pointer to the end of the file
        file_size=file.file.tell()##this gives current position of the pointer which is the size of the file
        file.file.seek(0)#reset pointer back at 0 posotion
        
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            #copyfileobj is used to copy the file object to the buffer which is the file path we created in the uploads folder but n effective way efficent way one at a time and not loading the whole file into memory

        logger.info("Saved file: %s", file_path)

        # ----------- 5. Run Prediction -----------
        result = predictor.predict_img(file_path)
        #prediciton time
        processing_time=time.time()-start_time
        logger.info(
            "Prediction => label=%s confidence=%.4f",
            result["label"], result["confidence"]
        )
        # Save prediction to database
        db_prediction=crud_prediction.create_prediction(
            db=db,
            user_id=current_user.id,
            filename=safe_filename,
            file_size=file_size,
            prediction_label=result['label'],
            confidence_score=result['confidence'],
            processing_time=processing_time,            
        )
        logging.info(f"saved prediction to db with id:{db_prediction.id}")
        
        return PredictionResponse(**result)

    except Exception as e:
        logger.exception("Unexpected server error")
        raise HTTPException(500, "Internal server error.") from e

    finally:
       # ----------- 6. Cleanup -----------
          if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("Deleted temp file: %s", file_path)
            except Exception:
                logger.exception("Failed to delete temp file")
                
                
#get predictions end point
#get prediction history
#in the above route the predictions was created in db now we are trying to access it 
@router.get("/predictions")
@limiter.limit("30/minute")
async def get_predictions(
    request: Request,
    skip:int=0,
    limit:int=100,
    db:Session=Depends(get_db),
    current_user: User= Depends(get_current_active_user)):
    if skip < 0:
        raise HTTPException(status_code=400, detail="Skip must be >= 0")
    
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
    
    predictions = crud_prediction.get_user_predictions(
        db, user_id=current_user.id, skip=skip, limit=limit
    )
    return {"predictions": predictions, "total": len(predictions)}


#{predictions_id} path parameter
#GET /api/predictions/1 
#Here 1 will be the prediction_id
@router.get("/predictions/{prediction_id}")
async def get_prediction(prediction_id: int, db:Session=Depends(get_db),current_user: User =Depends(get_current_active_user)):
    prediction=crud_prediction.get_prediction_by_id(db, prediction_id)
    
    if not prediction:
        raise HTTPException(status_code=404,detail='Prediction not found')
    
     #ensure the prediction belongs to the current user
    if prediction.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this prediction")

    return prediction

@router.get("/statistics")
@limiter.limit("20/minute")
async def get_statistics( request: Request,db:Session=Depends(get_db),current_user: User=Depends(get_current_active_user)):
    stats = crud_prediction.get_statistics(
        db, user_id=current_user.id
    )
    return stats
