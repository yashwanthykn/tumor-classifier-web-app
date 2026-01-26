#sql alchemy models

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.database import Base


class User(Base):
     __tablename__='users'
     id=Column(Integer,primary_key=True,index=True,autoincrement=True)
     email=Column(String(255),unique=True,index=True,nullable=False)
     username=Column(String(100), unique=True, index=True, nullable=False)
     hashed_password=Column(String(255), nullable=False)
     
     is_active=Column(Boolean, default=True)
     is_admin=Column(Boolean,default=False)
     
     created_at=Column(DateTime(timezone=True),server_default=func.now())
     
     #relationship to predictions one user has many predictions
     predictions=relationship("Prediction",back_populates="user")
     
     def __repr__(self):
          return f"<User(id={self.id}, email={self.email})>"

     
class Prediction(Base):
     __tablename__="predictions"
     
     id=Column(Integer,primary_key=True, index=True, autoincrement=True)
     
     #file info
     filename=Column(String(255),nullable=False)
     file_size=Column(Integer)
     
     #predictions results
     prediction_label=Column(String(50),nullable=False)
     confidence_score=Column(Float,nullable=False)
     
     #timestamps
     created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
     
     processing_time=Column(Float)
     
     #user authentication
     user_id=Column(Integer,ForeignKey("users.id"),nullable=False)
     
     #model version columns
     
     model_version=Column(String(50),default='vgg16_v1')
     
     
     
     
     #relationship back to user
     user=relationship("User",back_populates="predictions")
     
     #official string representation of the object for debugging and logging
     def __repr__(self):
          return f"Prediction(id={self.id},label={self.prediction_label},confidence={self.confidence_score})>"