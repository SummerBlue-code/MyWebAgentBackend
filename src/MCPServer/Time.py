import datetime
import json

from fastapi import FastAPI, Request, Response
from jsonrpcserver import Result, Success, dispatch, method
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@method(name='get_current_time')
def get_current_time():
    response = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return Success(response)


@app.post("/")
async def index(request: Request):
    return Response(dispatch(await request.body()))

@app.get("/tools")
def tools():
    functions_info = {
        "server_name": "TimeServer API",
        "version": "1.0",
        "available_functions": [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "以YYYY-MM-DD HH:MM:SS格式检索当前系统时间",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False
                    }
                }
            }
        ]
    }
    return functions_info



if __name__ == "__main__":
    uvicorn.run(app, port=8001)