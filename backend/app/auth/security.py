from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import os

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated='auto')

# JWT configurations
SECRET_KEY = os.getenv("SECRET_KEY", "UiMaV7qrSTXk2m51dMMiUXHbzAvVcK4lyHC3YZLknixPBP4vAdUU7udejZV")
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 30

"""verify password"""
def verify_password(plain_password: str, hashed_password: str) -> bool:
     return pwd_context.verify(plain_password, hashed_password)

"""Hash a password."""
def get_password_hash(password: str) -> str:
     if len(password.encode('utf-8')) > 72:
          password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
     return pwd_context.hash(password)



"""Create a JWT access token."""
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
     to_encode = data.copy()
     if expires_delta:
          expire = datetime.now(timezone.utc) + expires_delta
     else:
          expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

     to_encode.update({"exp": expire})
     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
     return encoded_jwt

"""Decode and validate a JWT token."""
def decode_access_token(token: str) -> Optional[dict]:
     try:
          payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
          return payload
     except JWTError:
          return None