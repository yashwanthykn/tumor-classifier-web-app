from datetime import datetime, timedelta,timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import os


#password hashing setups
# This creates a password manager all passwords rules are here.
pwd_context=CryptContext(schemes=["bcrypt"],deprecated='auto')

#JWT configurations
SECRET_KEY=os.getenv("SECRET_KEY")
ALGORITHM='HS256'
#HSAC-SHA256 creates a signature with SHA hash function
#signature=SHA256(message+secret_key)
#RS256 multiple servers uses public/private key pair
ACCESS_TOKEN_EXPIRE_MINUTES=30


def verify_password(plain_password:str,hashed_password:str)->bool:
     return pwd_context.verify(plain_password,hashed_password)
     """pwd_context.verify()
     takes the hash and extract the salt and hashes the input password with the same salt and compares the results matches returns True
     """
     
def get_password_hash(password:str)->str:
     return pwd_context.hash(password)
     #same process as mentioned above but this functions get triggered when user register or change password it generates a new hash with a new salt and stores in the database

def create_access_token(data:dict,expires_delta:Optional[timedelta]=None)->str:
     to_encode=data.copy()
     if expires_delta:
          expire=datetime.now(timezone.utc)
     else:
          expire=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
     """if expires_delta exist adds that to the current time or not exist addd 30 to the current time and set that as the expire time for the token"""
     
     to_encode.update({"exp":expire})
     #adding expire to the duplicate data dict i.e to_encode 
     
     encoded_jwt=jwt.encode(to_encode, SECRET_KEY,algorithm=ALGORITHM)
     """header_b64,payload_b64,signature=algo(mesage+secret_key)
     token=header_b64.payload_b64.signature_burl64
     reverse
     header_b64,payload_b64,signature=token.split('.')
     uses the requests header_64 and payload_64 and try to create a signatue and compares it with the signature in the token if matches then the token is valid and not tampered with"""
     return encoded_jwt


def decode_access_token(token:str)->Optional[dict]:
     try:
          payload=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
          return payload
     except JWTError:
          return None
     
     