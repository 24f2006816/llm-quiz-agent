from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from app.config import SECRET
from app.solver import solve_quiz_chain

app = FastAPI(title="LLM Analysis Quiz Solver")

class QuizRequest(BaseModel):
    email: str
    secret: str
    url: HttpUrl

@app.post("/solve")
async def solve_quiz(req: QuizRequest):
    if req.secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    try:
        result = await solve_quiz_chain(str(req.url), req.email, req.secret)
        return {"ok": True, "steps": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
