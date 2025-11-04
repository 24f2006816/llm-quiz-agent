from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.config import SECRET

app = FastAPI()

class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str

@app.post("/solve")
async def solve_quiz(request: QuizRequest):
    if request.secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    return {"status": "API is working!"}
