import logging
from typing import Dict, Any, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from src.GPTServer.GPTServer import GPTServer
from src.interface.ErrorCode import ErrorCode
from src.database.models import User
from datetime import datetime
import uuid

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

async def handle_register(register_data: dict) -> Tuple[bool, dict]:
    """处理用户注册
    
    Args:
        register_data (dict): 注册数据
        
    Returns:
        Tuple[bool, dict]: (是否成功, 响应数据)
    """
    try:
        # 验证必填字段
        if not register_data.get("username"):
            return False, {
                "error": "注册消息中缺少username",
                "code": ErrorCode.AUTH_INVALID_USERNAME.value
            }
        if not register_data.get("password"):
            return False, {
                "error": "注册消息中缺少password",
                "code": ErrorCode.AUTH_MISSING_PASSWORD.value
            }
        
        # 验证密码格式（至少8位，包含字母和数字）
        password = register_data["password"]
        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            return False, {
                "error": "密码必须至少8位，且包含字母和数字",
                "code": ErrorCode.AUTH_INVALID_PASSWORD.value
            }
        
        # 检查用户名是否已存在
        existing_user = GPTServer.db_ops.get_user_by_username(register_data["username"])
        if existing_user:
            return False, {
                "error": "该用户名已被注册",
                "code": ErrorCode.AUTH_USER_ALREADY_EXISTS.value
            }
        
        # 创建新用户
        user = User(
            user_id=str(uuid.uuid4()),
            username=register_data["username"],
            password=password,  # 注意：实际应用中应该对密码进行加密
            create_time=datetime.now(),
            settings=None
        )
        
        # 保存用户信息
        success = GPTServer.db_ops.create_user(user)
        if not success:
            return False, {
                "error": "用户注册失败",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value
            }
        
        logger.info(f"用户 {user.user_id} 注册成功")
        
        return True, {
            "user_id": user.user_id,
            "username": user.username
        }
        
    except Exception as e:
        logger.error(f"注册过程中发生错误: {str(e)}", exc_info=True)
        return False, {
            "error": "注册失败",
            "code": ErrorCode.SERVER_INTERNAL_ERROR.value
        }

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
    # 调用注册处理方法
    success, response = await handle_register(request.dict())

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