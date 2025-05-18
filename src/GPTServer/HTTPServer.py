import logging
from typing import Dict, Any, Tuple, List
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from src.GPTServer.KnowledgeBaseManager import KnowledgeBaseManager
from src.database.operations import DatabaseOperations
from src.database.base import Database
from src.interface.EnumModel import EnumModel
from src.interface.ErrorCode import ErrorCode
from src.database.models import User
from src.GPTServer.GPTServer import GPTServer
from datetime import datetime
import uuid
import os

from src.models.GPTModel import GPTModel
from src.config.GPTConfig import GPTConfig

logger = logging.getLogger(__name__)

# 创建配置实例
config = GPTConfig()

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

# 知识库相关请求模型
class CreateKnowledgeBaseRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    title: str = Field(..., description="知识库标题")

class KnowledgeBaseResponse(BaseModel):
    kb_id: str = Field(..., description="知识库ID")
    title: str = Field(..., description="知识库标题")
    created_time: datetime = Field(..., description="创建时间")

class KnowledgeBaseListResponse(BaseModel):
    knowledge_bases: List[KnowledgeBaseResponse] = Field(..., description="知识库列表")

class KnowledgeBaseFileResponse(BaseModel):
    file_id: str = Field(..., description="文件ID")
    file_name: str = Field(..., description="文件名")
    file_path: str = Field(..., description="文件路径")
    summary: str = Field(..., description="文件摘要")
    created_time: datetime = Field(..., description="创建时间")

class KnowledgeBaseFileListResponse(BaseModel):
    files: List[KnowledgeBaseFileResponse] = Field(..., description="文件列表")

# 全局服务实例
knowledge_base_service = KnowledgeBaseManager(
    db_ops=DatabaseOperations(
        Database(
            config.db_host,
            config.db_port,
            config.db_user,
            config.db_password,
            config.db_name
        )
    ),
    model=GPTModel(config.base_url,
                   config.api_key,
                   config.model
                   )
)

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

@app.post("/api/knowledge-base", 
    response_model=KnowledgeBaseResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="创建知识库",
    description="创建新的知识库"
)
async def create_knowledge_base(request: CreateKnowledgeBaseRequest) -> Dict[str, Any]:
    """创建知识库"""
    try:
        kb_id, title = knowledge_base_service.create_knowledge_base(request.user_id,request.title)
        return {
            "kb_id": kb_id,
            "title": title,
            "created_time": datetime.now()
        }
    except Exception as e:
        logger.error(f"创建知识库失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

@app.get("/api/knowledge-base", 
    response_model=KnowledgeBaseListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="获取知识库列表",
    description="获取用户的所有知识库"
)
async def get_knowledge_bases(user_id: str) -> Dict[str, Any]:
    """获取知识库列表"""
    try:
        knowledge_bases = knowledge_base_service.get_user_knowledge_bases(user_id)
        return {
            "knowledge_bases": [
                {
                    "kb_id": kb.kb_id,
                    "title": kb.title,
                    "created_time": kb.created_time
                }
                for kb in knowledge_bases
            ]
        }
    except Exception as e:
        logger.error(f"获取知识库列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

@app.get("/api/knowledge-base/{kb_id}/files", 
    response_model=KnowledgeBaseFileListResponse,
    responses={
        404: {"model": ErrorResponse, "description": "知识库不存在"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="获取知识库文件列表",
    description="获取指定知识库中的所有文件"
)
async def get_knowledge_base_files(kb_id: str) -> Dict[str, Any]:
    """获取知识库文件列表"""
    try:
        files = knowledge_base_service.get_knowledge_base_files(kb_id)
        return {
            "files": [
                {
                    "file_id": file.file_id,
                    "file_name": file.file_name,
                    "file_path": file.file_path,
                    "summary": file.summary,
                    "created_time": file.created_time
                }
                for file in files
            ]
        }
    except Exception as e:
        logger.error(f"获取知识库文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

@app.post("/api/knowledge-base/{kb_id}/files", 
    response_model=KnowledgeBaseFileResponse,
    responses={
        404: {"model": ErrorResponse, "description": "知识库不存在"},
        400: {"model": ErrorResponse, "description": "文件格式错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="上传文件到知识库",
    description="上传文件到指定的知识库"
)
async def upload_knowledge_file(
    kb_id: str,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """上传文件到知识库"""
    try:
        # 检查文件类型
        allowed_types = ['.txt', '.md', '.pdf', '.doc', '.docx']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "error",
                    "code": ErrorCode.INVALID_PARAMETER.value,
                    "message": f"不支持的文件类型: {file_ext}"
                }
            )

        result = await knowledge_base_service.update_file_to_knowledge_base(kb_id, file)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文件到知识库失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

@app.delete("/api/knowledge-base/{kb_id}", 
    responses={
        404: {"model": ErrorResponse, "description": "知识库不存在"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="删除知识库",
    description="删除指定的知识库及其所有文件"
)
async def delete_knowledge_base(kb_id: str) -> Dict[str, Any]:
    """删除知识库"""
    try:
        knowledge_base_service.delete_knowledge_base(kb_id)
        return {"message": "知识库删除成功"}
    except Exception as e:
        logger.error(f"删除知识库失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

@app.delete("/api/knowledge-base/{kb_id}/files/{file_id}",
    responses={
        404: {"model": ErrorResponse, "description": "文件不存在"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="删除知识库文件",
    description="删除指定的知识库文件"
)
async def delete_knowledge_file(kb_id: str, file_id: str) -> Dict[str, Any]:
    """删除知识库文件"""
    try:
        # 检查知识库是否存在
        knowledge_base = knowledge_base_service.db_ops.get_knowledge_base(kb_id)
        if not knowledge_base:
            raise HTTPException(
                status_code=404,
                detail={
                    "type": "error",
                    "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                    "message": "知识库不存在"
                }
            )

        # 检查文件是否存在
        file = knowledge_base_service.db_ops.get_knowledge_base_file(file_id)
        if not file:
            raise HTTPException(
                status_code=404,
                detail={
                    "type": "error",
                    "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                    "message": "文件不存在"
                }
            )

        knowledge_base_service.delete_knowledge_base_file(kb_id, file_id)
        return {"message": "文件删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库文件失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "code": ErrorCode.SERVER_INTERNAL_ERROR.value,
                "message": str(e)
            }
        )

def start_http_server():
    """启动HTTP服务器"""
    import uvicorn
    logger.info(f"HTTP服务器启动在 {config.http_host}:{config.http_port}")
    uvicorn.run(app, host=config.http_host, port=config.http_port)

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 启动HTTP服务器
    start_http_server() 