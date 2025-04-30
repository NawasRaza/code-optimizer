from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.optimizer.code_optimizer import optimize_python_code
from app.report.report_generator import generate_report
from app.models.code_model import CodeInput
import os

app = FastAPI(title="Python Code Optimizer")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the HTML file
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

# Optimize code endpoint
@app.post("/api/optimize")
async def optimize_code(code_input: CodeInput):
    try:
        optimized_code = optimize_python_code(code_input.code)
        return {"optimized_code": optimized_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

# Export report endpoint
@app.get("/api/report/export")
async def export_report(format: str, optimized_code: str):
    try:
        file_path = generate_report(optimized_code, format)
        return FileResponse(
            file_path,
            media_type=f"application/{format}",
            filename=f"optimization_report.{format}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")