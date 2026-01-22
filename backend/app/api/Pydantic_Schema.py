from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class PredictionResponse(BaseModel):
     label:str
     confidence:float
     
     
"""
pydantic data validation library

Controls API output format

Self-documentation for FastAPI

Prevents inconsistent responses"""


#Validates user registration data
class UserCreate(BaseModel):
     email:EmailStr
     username:str
     password:str

# Validates login credentials
class Userlogin(BaseModel):
     email:EmailStr
     password:str

#Defines what user data looks like when sent to user
class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime
    
    class Config:
         from_attributes=True
         #allos sqlalchmey model conversions to pydantic models


#what you return after successful login         
class Token(BaseModel):
     access_token:str
     token_type:str
     
#What's inside the JWT token after decoding
class TokenData(BaseModel):
     email:Optional[str]=None
     
     