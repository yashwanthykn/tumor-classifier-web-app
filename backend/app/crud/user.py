from sqlalchemy.orm import Session
from app.database.models import User

from typing import Optional

from app.auth.security import get_password_hash
from app.auth.security import verify_password


def get_user_by_email(db:Session,email:str)->Optional[User]:
     return db.query(User).filter(User.email==email).first()


def get_user_by_username(db:Session,username:str)->Optional[User]:
     return db.query(User).filter(User.username==username).first()

def get_user_by_id(db:Session, user_id:int)->Optional[User]:
     return db.query(User).filter(User.id==user_id).first()


def create_user(db:Session, email:str, username:str, password:str)->User:
     hash_password=get_password_hash(password)
     db_user=User(
          email=email,
          username=username,
          hashed_password=hash_password
     )
     
     db.add(db_user)
     db.commit()
     db.refresh(db_user)
     
     return db_user


def authenticate_user(db:Session,email:str,password:str)->Optional[User]:
     
     user=get_user_by_email(db,email)
     
     if not user:
          return None
     if not verify_password(password,user.hashed_password):
          return None
     
     return user