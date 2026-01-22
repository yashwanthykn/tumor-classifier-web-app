from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database.database import get_db
from app.crud import user as crud_user
from app.auth.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.api.Pydantic_Schema import UserCreate, UserResponse, Userlogin, Token
from app.auth.dependencies import get_current_active_user
from app.database.models import User
from app.middleware.rate_limit import limiter 


#router creation
router=APIRouter()

@router.post("/register",response_model=UserResponse,status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def register_user(request: Request,user_data:UserCreate, db:Session=Depends(get_db)):
     #check if user email exists already
     db_user=crud_user.get_user_by_email(db,user_data.email)

     if db_user:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Email already registered"
          )
     
     #check if the username is already exists
     db_user=crud_user.get_user_by_username(db,username=user_data.username)
     if db_user:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Username already exists"
          )
     
     # Validate password strength
     if len(user_data.password) < 8:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Password must be at least 8 characters long"
          )
    

     #create the user 
     new_user=crud_user.create_user(
          db=db,
          email=user_data.email,
          username=user_data.username,
          password=user_data.password     
     )
     
     return new_user

@router.post("/login",response_model=Token)
@limiter.limit("10/minute")
def login_user( request: Request,user_data:Userlogin,db:Session=Depends(get_db)):
     user=crud_user.authenticate_user(db=db,
                                      email=user_data.email,
                                      password=user_data.password)
     
     if user is None:
          raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Invalid email or password",
               headers={"WWW-Authenticate": "Bearer"},
          )
          
     
     access_token_expires =timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
     access_token=create_access_token(
          data={"sub":user.email},
          expires_delta=access_token_expires
     )


     return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me",response_model=UserResponse)
@limiter.limit("30/minute")
def get_current_user_info( request: Request,current_user:User=Depends(get_current_active_user)):
     return current_user          