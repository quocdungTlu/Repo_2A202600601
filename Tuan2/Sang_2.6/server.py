import os
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from prompt import generate_demo_results

app = FastAPI()

@app.get('/api/demo')
async def api_demo():
    try:
        data = generate_demo_results()
        return {"success": True, "data": data}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)}
        )

@app.get('/', response_class=FileResponse)
async def root():
    return FileResponse('index.html')

@app.get('/{path:path}')
async def serve_static(path: str):
    file_path = os.path.join('.', path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail='File not found')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('server:app', host='0.0.0.0', port=8000, reload=True)
