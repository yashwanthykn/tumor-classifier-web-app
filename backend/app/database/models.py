from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to predictions
    predictions = relationship("Prediction", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
   

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # File info
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer)

    # Prediction results
    prediction_label = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processing_time = Column(Float)

    # User relationship
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Model version
    model_version = Column(String(50), default='vgg16_v1')

    # Relationship back to user
    user = relationship("User", back_populates="predictions")

    def __repr__(self):
        return f"<Prediction(id={self.id}, label={self.prediction_label})>"