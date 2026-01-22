"""reads JWT tokens snet by the user,checks if its valid """


from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.auth.security import decode_access_token
from app.crud import user as crud_user
from app.database.models import User


#HTTP Bearer Scheme : this tell fastapi "Everytime i use this dependency i expect a Bearer token in request header.
# missed header 403 error "
security=HTTPBearer()


def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(security),db:Session=Depends(get_db))->User:
     
     
     credentials_exception = HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Could not validate credentials",
          headers={"WWW-Authenticate": "Bearer"},
     )
     
     #extracting the token from the reques header 
     """Authorization : Bearer abc.eg.hijk...
     then credentials.credentials will be abc.efg...."""
     token=credentials.credentials
     #Decode the token 
     payload=decode_access_token(token)
     
     if payload is None:
          raise credentials_exception
     email:str=payload.get("sub")
     if email is None:
          raise credentials_exception
     
     #Now get the user by email from the database
     
     user=crud_user.get_user_by_email(db,email=email)
     
     if user is None:
          raise credentials_exception
     
     if user.is_active:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Inactive user"
          )
          
     return user

def get_current_active_user(current_user:User=Depends(get_current_user))->User:
     
     if not current_user.is_active:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Inactive user"
          )
     return current_user
