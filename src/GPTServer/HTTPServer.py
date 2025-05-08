import logging
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from src.GPTServer.GPTServer import GPTServer
from src.interface.ErrorCode import ErrorCode

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="GPT Server API",
    description="GPT服务器的HTTP API接口",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
)

# 请求模型
class RegisterRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码，至少8位，包含字母和数字")

# 响应模型
class RegisterResponse(BaseModel):
    type: str = Field(..., description="响应类型")
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")

class ErrorResponse(BaseModel):
    type: str = Field(..., description="响应类型")
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")

@app.post("/api/register", 
    response_model=RegisterResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="用户注册",
    description="注册新用户，需要提供用户名和密码"
)
async def register(request: RegisterRequest) -> Dict[str, Any]:
    """处理注册请求"""
    # try:
    # 调用注册处理方法
    success, response = await GPTServer.handle_register(request.dict())

    if success:
        return {
            "type": "register_success",
            **response
        }
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "type": "error",
                "code": response["code"],
                "message": response["error"]
            }
        )
            
    # except Exception as e:
    #     logger.error(f"处理注册请求时发生错误: {str(e)}", exc_info=True)
    #     raise HTTPException(
    #         status_code=500,
    #         detail={
    #             "type": "error",
    #             "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
    #             "message": "服务器内部错误"
    #         }
    #     )

def start_http_server():
    """启动HTTP服务器"""
    import uvicorn
    uvicorn.run(app, host="localhost", port=8080)

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 启动HTTP服务器
    start_http_server() 