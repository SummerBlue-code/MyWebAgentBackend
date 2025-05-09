import json
import logging
from typing import Dict, Optional
from datetime import datetime
import uuid

from websockets import ServerConnection

from src.interface import Messages
from src.interface.EnumModel import EnumModel
from src.interface.MCPServers import MCPServers
from src.interface.WebsocketMessage import WebsocketMessage
from src.GPTServer.HeartbeatManager import HeartbeatManager
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import MessageProcessingError, ToolExecutionError
from src.database.models import Message

logger = logging.getLogger(__name__)

class MessageHandler:
    """WebSocket消息处理器"""
    
    def __init__(self, gpt_server):
        """初始化消息处理器
        
        Args:
            gpt_server: GPTServer实例，用于访问数据库和模型
        """
        self.conversation_manager = gpt_server.conversation_manager
        self.db_ops = gpt_server.db_ops
        
    async def handle_message(
        self,
        websocket: ServerConnection,
        message: str,
        user_id: str,
        heartbeat_manager: HeartbeatManager
    ) -> None:
        """处理单条WebSocket消息
        
        Args:
            websocket (ServerConnection): WebSocket连接
            message (str): 消息内容
            user_id (str): 用户ID
            heartbeat_manager (HeartbeatManager): 心跳管理器
        """
        if heartbeat_manager.handle_message(message):
            return
            
        websocket_message = WebsocketMessage(message)
        message_type = websocket_message.get_type()
        logger.info('message_type: %s', message_type)
        
        message_handlers = {
            "logout": lambda: websocket.send(MessageFormat.create_logout_success_response()),
            MessageFormat.RequestType.SETTINGS_ADD_SERVER.value: lambda: self.conversation_manager.gpt_server.settings_user_server(
                websocket_message.get_server(),
                user_id
            ),
            MessageFormat.RequestType.CONVERSATION_QUESTION.value: lambda: self.conversation_manager.answer_conversation_question(
                websocket_message.get_question(),
                user_id,
                websocket_message.get_mcp_servers()
            ),
            MessageFormat.RequestType.CONVERSATION_MESSAGE.value: lambda: self.conversation_manager.answer_conversation_message(
                websocket_message.get_conversation_id(),
                user_id
            ),
            MessageFormat.RequestType.QUESTION.value: lambda: self.conversation_manager.answer_question(
                websocket_message.get_question(),
                user_id,
                websocket_message.get_conversation_id(),
                websocket_message.get_mcp_servers(),
            ),
            MessageFormat.RequestType.EXECUTE_TOOLS.value: lambda: self.conversation_manager.answer_question_with_tools(
                websocket_message.get_question(),
                user_id,
                websocket_message.get_conversation_id(),
                websocket_message.get_select_functions(),
                websocket_message.get_mcp_servers()
            )
        }
        
        handler = message_handlers.get(message_type)
        if handler:
            await handler()
        else:
            error_msg = f"未知消息类型: {message_type}"
            logger.warning(error_msg)
            await websocket.send(MessageFormat.create_error_response(
                error_msg,
                ErrorCode.MSG_INVALID_TYPE.value
            ))

    async def handle_message_error(self, websocket: ServerConnection, error: Exception) -> None:
        """处理消息处理过程中的错误
        
        Args:
            websocket (ServerConnection): WebSocket连接
            error (Exception): 错误对象
        """
        if isinstance(error, json.JSONDecodeError):
            error_msg = f"JSON解析错误: {str(error)}"
            error_code = ErrorCode.MSG_JSON_PARSE_ERROR.value
        elif isinstance(error, MessageProcessingError):
            error_msg = f"消息处理错误: {str(error)}"
            error_code = error.error_code.value
        elif isinstance(error, ToolExecutionError):
            error_msg = f"工具执行错误: {str(error)}"
            error_code = error.error_code.value
        else:
            error_msg = f"未知错误: {str(error)}"
            error_code = ErrorCode.SERVER_INTERNAL_ERROR.value
            
        logger.error(error_msg, exc_info=True)
        await websocket.send(MessageFormat.create_error_response(
            error_msg,
            error_code
        ))

    async def send_initial_data(self, websocket: ServerConnection, user_id: str) -> None:
        """发送初始数据（对话记录和用户设置）
        
        Args:
            websocket (ServerConnection): WebSocket连接
            user_id (str): 用户ID
        """
        # 获取并发送对话记录
        conversations = self.db_ops.get_user_conversations(user_id)
        logger.info(f"获取到用户 {user_id} 的对话记录: {conversations}")
        if conversations:
            await websocket.send(
                MessageFormat.create_conversation_list_response(
                    conversations
                )
            )
            
        # 获取并发送用户设置
        user_settings = self.db_ops.get_user_settings(user_id)
        logger.info(f"获取到用户 {user_id} 的服务器设置: {user_settings}")
        if user_settings:
            await websocket.send(
                MessageFormat.create_user_settings_response(
                    user_settings
                )
            ) 