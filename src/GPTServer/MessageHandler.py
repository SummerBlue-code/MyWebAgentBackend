import json
import logging
from typing import Dict, Optional
from datetime import datetime
import uuid

from websockets import ServerConnection

from src.GPTServer.AuthenticationHandler import AuthenticationHandler
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
        self.gpt_server = gpt_server
        
    async def handle_message(
        self,
        websocket: ServerConnection,
        message: str,
        user_id: str,
        heartbeat_manager: HeartbeatManager,
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

        try:
            question = websocket_message.get_question()
            knowledge_base_id = websocket_message.get_knowledge_base_id()
        except Exception as e:
            logger.error(f"获取问题或知识库ID失败: {str(e)}", exc_info=True)
            return


        if question and knowledge_base_id:
            # 如果存在知识库ID，搜索相关知识
            knowledge_base_id = websocket_message.get_knowledge_base_id()
            if knowledge_base_id:
                try:
                    # 获取用户最后一条消息
                    last_user_message = question
                    
                    if last_user_message:
                        # 搜索知识库
                        from src.GPTServer.KnowledgeBaseManager import KnowledgeBaseManager
                        kb_manager = KnowledgeBaseManager(self.db_ops, self.gpt_server.conversation_manager.model)
                        search_results = kb_manager.search_texts_in_knowledge_base(
                            knowledge_base_id, 
                            last_user_message
                        )
                        
                        # 构建知识库提示词
                        if search_results:
                            knowledge_prompt = ""
                            for index, doc in enumerate(search_results):
                                knowledge_prompt += f"{index+1}. {doc}\n\n"
                            
                            self.gpt_server.system_prompts = """# 角色定义
你叫"智链",是一个专业的AI助手,你的回答必须严格遵守以下规则:

# 回答规则
1.用户的问题必须使用中文回答
2.精通各种工具函数的调用,具备跨平台数据接口调用权限,能够精准解析用户需求并调用最佳工具函数获取结构化数据
3.精通多种编程语言、框架、设计模式和最佳实践,通晓17种编程范式,擅长模块化设计(含DDD/微服务架构),代码生成通过ISO/IEC 5055认证
4.用户的问题必须严格基于以下上下文内容回答：
4-1.当上下文内容无法回答问题, 并且此时调用工具函数如果有可能解决问题, 那么你会去调用工具函数
4-2.当上下文内容无法回答问题，并且调用的工具函数返回的信息也无法解决问题，那么你会回答"对不起，这个问题我无法回答，因为我目前没有掌握足够的信息。请您按照以下操作来增加解决的可能性:\n1.提供更详细的问题\n2.向知识库添加更多的相关文件\n3.添加更多有助于我解决问题的工具函数"

# 上下文
{{context}}
"""

                            # 将知识库内容添加到system message
                            self.gpt_server.system_prompts = self.gpt_server.system_prompts.replace("{{context}}", knowledge_prompt)
                except Exception as e:
                    logger.error(f"搜索知识库失败: {str(e)}", exc_info=True)
                    # 如果搜索失败，继续使用原有方式回答
        else:
            self.gpt_server.system_prompts = """# 角色定义
你叫"智链",是一个专业的AI助手,你的回答必须严格遵守以下规则:

# 回答规则
1.用户的问题必须使用中文回答
2.精通各种工具函数的调用,具备跨平台数据接口调用权限,能够精准解析用户需求并调用最佳工具函数获取结构化数据
3.精通多种编程语言、框架、设计模式和最佳实践,通晓17种编程范式,擅长模块化设计(含DDD/微服务架构),代码生成通过ISO/IEC 5055认证
"""

        
        message_handlers = {
            "logout": lambda: websocket.send(MessageFormat.create_logout_success_response()),
            MessageFormat.RequestType.SETTINGS_ADD_SERVER.value: lambda: AuthenticationHandler(self.db_ops).settings_user_server(
                websocket_message.get_server(),
                user_id,
                websocket_manager=self.gpt_server.websocket_manager,
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
            ),
            MessageFormat.RequestType.DELETE_CONVERSATION.value: lambda: self.conversation_manager.delete_conversation(
                websocket_message.get_conversation_id(),
                user_id
            ),
            MessageFormat.RequestType.GET_CONVERSATION_LIST.value: lambda: self.conversation_manager.get_conversation_list(
                user_id
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