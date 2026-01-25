from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

#reading database url from the environment variable in docker compose file and db container 

DATABASE_URL=os.getenv('DATABASE_URL',
                       'postgresql://tumor_user:tumor_pass_secure_123@localhost:5432/tumor_classifier_db')


#creating the engine

#create database connection manager
#We use engine to connect to the database


engine=create_engine(
     DATABASE_URL,
     pool_pre_ping=True, #checks connections health before using 
     echo=True #need to set this Flase in productions so no logs
)


#evertyhing i do to the db during this request all the changes add deleting are made using this 

#bind make sure the session uses the database what kind of engine datbase connections

#************************
# sessionmaker creates sessions using the Session class internally
#************************
SessionLocal=sessionmaker(
     autocommit=False,
     autoflush=False,
     bind=engine
)


Base=declarative_base()
#Base helps in creating a regitry the list of tables and schemea created eay work and also help us in making tables as python classes

def get_db():
     db=SessionLocal()
     try:
          yield db
     finally:
          db.close()