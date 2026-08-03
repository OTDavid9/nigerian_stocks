from pymongo import MongoClient
from core.config import MONGODB_URI, DATABASE_NAME


client = MongoClient(MONGODB_URI)

db = client[DATABASE_NAME] # type: ignore

users_collection = db.users
users_documents = db.documents
stocks_data = db.stocks_data
stocks_reports = db.stocks_reports