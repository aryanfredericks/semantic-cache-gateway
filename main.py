import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os
load_dotenv()

from utils.groq_provider import GroqProvider

api_key = os.getenv("GROQ_API_KEY")

app = FastAPI(title="AI Agent Query Service")
provider = GroqProvider(api_key=api_key)

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The input query for the Groq model")

@app.post("/query")
async def handle_query(request_body: QueryRequest):
    clean_query = request_body.query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Please provide a valid, non-empty query."
        )

    try:
        result = await provider.call(clean_query)   
        return {"message": result}

    except Exception as e:
        logging.error(f"Groq API Call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the AI request: {str(e)}"
        )

@app.get("/health")
def health_check():
    return {"status": "healthy"}