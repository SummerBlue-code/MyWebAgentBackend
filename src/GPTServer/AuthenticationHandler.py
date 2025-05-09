import json
import logging
import asyncio
from typing import Tuple
import uuid
from datetime import datetime

from websockets import ServerConnection

from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import AuthenticationError, GPTServerError
from src.database.models import User
from src.database.operations import DatabaseOperations

logger = logging.getLogger(__name__)

class AuthenticationHandler:
    """WebSocket认证处理器"""
    
    def __init__(self, db_ops: DatabaseOperations):
        """初始化认证处理器
        
        Args:
            db_ops (DatabaseOperations): 数据库操作实例
        """
        self.db_ops = db_ops
        
    async def handle_auth(self, websocket: ServerConnection, auth_data: dict) -> User:
        """处理用户认证
        
        Args:
            websocket (ServerConnection): WebSocket连接
            auth_data (dict): 认证数据
            
        Returns:
            User: 认证成功的用户对象
            
        Raises:
            AuthenticationError: 认证失败时抛出
        """
        auth_type = auth_data.get("type")
        if not auth_type:
            raise AuthenticationError("认证消息中缺少type字段", ErrorCode.AUTH_MISSING_TYPE)
            
        if auth_type == "login":
            # 用户名密码登录
            username = auth_data.get("username")
            password = auth_data.get("password")
            
            if not username:
                raise AuthenticationError("认证消息中缺少username", ErrorCode.AUTH_MISSING_USERNAME)
            if not password:
                raise AuthenticationError("认证消息中缺少password", ErrorCode.AUTH_MISSING_PASSWORD)
                
            user = self.db_ops.get_user_by_username(username)
            if not user:
                raise AuthenticationError("用户不存在", ErrorCode.AUTH_USER_NOT_FOUND)
                
            # 验证密码（实际应用中应该使用加密后的密码比较）
            if user.password != password:
                raise AuthenticationError("密码错误", ErrorCode.AUTH_INVALID_PASSWORD)
            
            # 发送登录成功消息
            await websocket.send(
                MessageFormat.create_auth_success_response(
                    user_id=user.user_id,
                    username=user.username
                )
            )
                
            return user
            
        else:
            raise AuthenticationError(f"不支持的认证类型: {auth_type}", ErrorCode.AUTH_INVALID_TYPE)
        
    async def handle_authentication(self, websocket: ServerConnection) -> Tuple[User, str]:
        """处理用户认证流程
        
        Args:
            websocket (ServerConnection): WebSocket连接
            
        Returns:
            Tuple[User, str]: (用户对象, 用户ID)
            
        Raises:
            AuthenticationError: 认证失败时抛出
            json.JSONDecodeError: JSON解析错误时抛出
        """
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
        logger.info(f"获取到认证消息: {auth_msg}")
        
        try:
            auth_data = json.loads(auth_msg)
            user = await self.handle_auth(websocket, auth_data)
            return user, user.user_id
        except AuthenticationError as e:
            logger.error(f"认证错误: {str(e)}", exc_info=True)
            await websocket.send(MessageFormat.create_error_response(
                str(e),
                e.error_code.value
            ))
            await websocket.close(code=1008, reason=str(e))
            raise
        except json.JSONDecodeError as e:
            logger.error(f"认证消息格式错误: {str(e)}", exc_info=True)
            await websocket.send(MessageFormat.create_error_response(
                "认证消息格式错误",
                ErrorCode.AUTH_INVALID_FORMAT.value
            ))
            await websocket.close(code=1008, reason="认证消息格式错误")
            raise
            
    async def handle_register(self, register_data: dict) -> tuple[bool, dict]:
        """处理用户注册
        
        Args:
            register_data (dict): 注册数据
            
        Returns:
            tuple[bool, dict]: (是否成功, 响应数据)
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
            existing_user = self.db_ops.get_user_by_username(register_data["username"])
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
            success = self.db_ops.create_user(user)
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

    async def settings_user_server(self, server: dict, user_id: str, websocket_manager) -> None:
        """设置用户服务器
        
        Args:
            server (dict): 服务器配置信息
            user_id (str): 用户ID
            websocket_manager: WebSocket管理器实例
        """
        try:
            logger.info(f"正在设置用户 {user_id} 的服务器配置")
            logger.info(f"服务器配置信息: {server}")
            
            # 更新用户服务器设置
            success = self.db_ops.update_user_server(server, user_id)
            
            if success:
                logger.info(f"用户 {user_id} 的服务器设置已成功更新")
                # 获取更新后的设置
                user_settings = self.db_ops.get_user_settings(user_id)
                # 发送更新后的设置给用户
                await websocket_manager.send_to_user(
                    user_id,
                    MessageFormat.create_user_settings_response(
                        user_settings
                    )
                )
            else:
                logger.error(f"用户 {user_id} 的服务器设置更新失败")
                raise GPTServerError("服务器设置更新失败", ErrorCode.SERVER_SETTINGS_UPDATE_ERROR)
                
        except Exception as e:
            logger.error(f"设置用户服务器时发生错误: {str(e)}")
            raise GPTServerError(f"设置用户服务器失败: {str(e)}", ErrorCode.SERVER_SETTINGS_UPDATE_ERROR) 