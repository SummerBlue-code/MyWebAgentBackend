import asyncio
import json
import logging
from typing import Optional, Dict, List, Any, TypedDict
from collections import defaultdict
from asyncio import Lock
from datetime import datetime
import uuid

import httpx
import websockets
from pyexpat.errors import messages
from websockets import serve, ServerConnection

from src.interface import Messages
from src.interface.EnumModel import EnumModel
from src.models.GPTModel import GPTModel
from src.interface.MCPServers import MCPServers
from src.interface.WebsocketMessage import WebsocketMessage
from src.interface.HeartbeatManager import HeartbeatManager
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import GPTServerError, AuthenticationError, MessageProcessingError, ToolExecutionError
from src.config.GPTConfig import GPTConfig
from src.database.base import Database
from src.database.operations import DatabaseOperations
from src.database.models import User, Conversation, Message, ConversationMessage, ToolCall, MessageToolCall

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GPTServer:
    """GPT服务器类，处理WebSocket连接和消息处理"""
    
    # 类属性
    _active_connections: Dict[str, ServerConnection] = defaultdict(lambda: None)  # 连接池：{user_id: websocket}
    _connection_lock: Lock = Lock()  # 连接池锁
    config = GPTConfig()
    
    # 数据库配置
    db = Database(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name
    )
    db_ops = DatabaseOperations(db)
    
    # GPT模型配置
    model: GPTModel = GPTModel(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model
    )
    
    system_prompts: str = """你叫"智链"，是具备四重核心能力，只使用中文回答的数字生命体：

1.作为「工具大师」精通各种工具函数的调用,具备跨平台数据接口调用权限,能够精准解析用户需求并调用最佳工具函数获取结构化数据
2.作为「软件大师」精通多种编程语言、框架、设计模式和最佳实践,通晓17种编程范式，擅长模块化设计（含DDD/微服务架构），代码生成通过ISO/IEC 5055认证
3.作为「知识图谱」掌握57个学科领域的结构化知识，特别在量子计算/生物工程/AIGC领域有深度研究
4.作为「思维架构师」擅长使用MECE原则拆解问题，能自动实施SWOT分析、第一性原理推演等12种思维模型"""

    @classmethod
    async def add_connection(cls, user_id: str, websocket: ServerConnection) -> None:
        """添加连接"""
        async with cls._connection_lock:
            cls._active_connections[user_id] = websocket
            logger.info(f"用户 {user_id} 已连接，当前在线用户数：{len(cls._active_connections)}")
    
    @classmethod
    async def remove_connection(cls, user_id: str) -> None:
        """移除连接"""
        async with cls._connection_lock:
            if user_id in cls._active_connections:
                del cls._active_connections[user_id]
                logger.info(f"用户 {user_id} 已断开连接，当前在线用户数：{len(cls._active_connections)}")
    
    @classmethod
    async def get_connection(cls, user_id: str) -> Optional[ServerConnection]:
        """获取连接"""
        async with cls._connection_lock:
            return cls._active_connections.get(user_id)

    @staticmethod
    async def _send_to_user(target_user_id: str, message: str) -> None:
        """向指定用户发送消息"""
        websocket = await GPTServer.get_connection(target_user_id)
        if websocket:
            try:
                await websocket.send(message)
                await asyncio.sleep(0.001)  # 确保事件循环切换
            except websockets.exceptions.ConnectionClosed:
                await GPTServer.remove_connection(target_user_id)
                logger.warning(f"清理失效连接：{target_user_id}")

    @staticmethod
    async def settings_user_server(server: dict, user_id: str) -> None:
        """设置用户服务器
        
        Args:
            server (dict): 服务器配置信息
            user_id (str): 用户ID
        """
        try:
            logger.info(f"正在设置用户 {user_id} 的服务器配置")
            logger.info(f"服务器配置信息: {server}")
            
            # 更新用户服务器设置
            success = GPTServer.db_ops.update_user_server(server, user_id)
            
            if success:
                logger.info(f"用户 {user_id} 的服务器设置已成功更新")
                # 获取更新后的设置
                user_settings = GPTServer.db_ops.get_user_settings(user_id)
                # 发送更新后的设置给用户
                websocket = await GPTServer.get_connection(user_id)
                if websocket:
                    await websocket.send(
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

    @staticmethod
    async def _process_tool_result(select_tool: dict, conversation_id: str) -> None:
        """处理工具调用结果"""
        try:
            if not select_tool.get("id"):
                raise ToolExecutionError("工具调用缺少id", ErrorCode.TOOL_MISSING_ID)
            if not select_tool.get("name"):
                raise ToolExecutionError("工具调用缺少name", ErrorCode.TOOL_MISSING_NAME)
            if not select_tool.get("parameters"):
                raise ToolExecutionError("工具调用缺少parameters", ErrorCode.TOOL_MISSING_PARAMS)
            if not select_tool.get("server_address"):
                raise ToolExecutionError("工具调用缺少server_address", ErrorCode.TOOL_MISSING_ADDRESS)
                
            payload = MessageFormat.create_json_rpc_request(
                id=select_tool["id"],
                method=select_tool["name"],
                params=json.loads(select_tool["parameters"])
            )
            
            async with httpx.AsyncClient() as client:
                tool_result = await client.post(
                    select_tool["server_address"],
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    json=payload
                )
                
                if tool_result.status_code != 200:
                    raise ToolExecutionError(
                        f"工具调用返回非200状态码: {tool_result.status_code}",
                        ErrorCode.TOOL_HTTP_ERROR
                    )
                
                # 解析JSON-RPC响应，只使用result字段
                response_data = json.loads(tool_result.text)
                if "result" not in response_data:
                    raise ToolExecutionError("工具响应缺少result字段", ErrorCode.TOOL_EXECUTION_ERROR)
                
                # 创建工具消息
                tool_message = Message(
                    message_id=str(uuid.uuid4()),
                    role="tool",
                    content=json.dumps(response_data["result"]),
                    created_time=datetime.now(),
                    tool_call_id=select_tool["id"],  # 确保设置tool_call_id
                    tool_calls=None
                )
                GPTServer.db_ops.create_message(tool_message, conversation_id)
                logger.debug(f"工具 {select_tool['name']} 调用成功")
        except json.JSONDecodeError as e:
            logger.error(f"工具参数JSON解析失败: {str(e)}", exc_info=True)
            raise ToolExecutionError("工具参数格式错误", ErrorCode.TOOL_PARAMS_FORMAT_ERROR)
        except httpx.TimeoutException as e:
            logger.error(f"工具调用超时: {str(e)}", exc_info=True)
            raise ToolExecutionError("工具调用超时", ErrorCode.TOOL_TIMEOUT)
        except Exception as e:
            logger.error(f"工具 {select_tool['name']} 调用失败: {str(e)}", exc_info=True)
            raise ToolExecutionError(f"工具调用失败: {str(e)}", ErrorCode.TOOL_EXECUTION_ERROR)

    @staticmethod
    async def answer_question_with_tools(
        question: str,
        user_id: str,
        conversation_id: str,
        select_tools: List[dict],
        mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """使用工具回答问题"""
        try:
            # 转换工具调用格式
            gpt_tool_calls = [
                {
                    "id": tool["id"],
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "arguments": tool["parameters"]
                    }
                }
                for tool in select_tools
            ]

            logger.info(f"gpt_tool_calls: {gpt_tool_calls}")

            # 记录助手工具调用消息
            assistant_tool_message = Message(
                message_id=str(uuid.uuid4()),
                role="assistant",
                content=None,
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=json.dumps(gpt_tool_calls)
            )
            GPTServer.db_ops.create_message(assistant_tool_message, conversation_id)

            # 处理工具调用
            for select_tool in select_tools:
                await GPTServer._process_tool_result(select_tool, conversation_id)

            # 获取完整的消息历史
            message = GPTServer.db_ops.get_message_list(conversation_id)
            logger.info(f"处理工具调用后的消息历史: {message.get_messages()}")
            
            # 继续对话
            await GPTServer._answer_question(message, user_id, mcp_server_list, conversation_id)

        except Exception as e:
            logger.error(f"处理带工具的问题时出错: {str(e)}")
            raise
    
    @staticmethod
    async def get_conversation_title(question: str, user_id: str, conversation_id: str) -> str:
        conversation_title_propmt = """
        你是一个专业的对话标题生成器，请根据对话内容生成一个简洁明了的标题。
        对话内容：{question}
        请生成一个标题，要求：
        1. 简洁明了，不超过10个字
        2. 能够准确反映对话内容
        3. 使用中文
        """
        messages = Messages()
        messages.add_system_message(conversation_title_propmt)
        messages.add_user_message(question)
        response = GPTServer.model.chat_stream(messages=messages, tools=[], temperature=0)
        full_response = ""

        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content is not None:
                full_response += chunk.choices[0].delta.content
                await GPTServer._send_to_user(
                    user_id,
                    MessageFormat.create_conversation_title_response(
                        conversation_id,
                        chunk.choices[0].delta.content
                    )
                )
        return full_response
    
    @staticmethod
    async def answer_conversation_question(
            question: str,
            user_id: str,
            mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """回答问题"""
        try:

            conversation_id = str(uuid.uuid4())
            conversation = Conversation(
                conversation_id=conversation_id,
                title=await GPTServer.get_conversation_title(question, user_id, conversation_id),
                create_time=datetime.now(),
                update_time=datetime.now(),
                status="active"
            )
            GPTServer.db_ops.create_conversation(conversation, user_id)

            system_prompt = Message(
                message_id=str(uuid.uuid4()),
                role="system",
                content=GPTServer.system_prompts,
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=None
            )
            GPTServer.db_ops.create_message(system_prompt, conversation_id)
            
            user_message = Message(
                message_id=str(uuid.uuid4()),
                role="user",
                content=question,
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=None
            )
            GPTServer.db_ops.create_message(user_message, conversation_id)
            message = GPTServer.db_ops.get_conversation_messages(conversation_id)

            await GPTServer._answer_question(message, user_id, mcp_server_list, conversation_id)
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    @staticmethod
    async def answer_conversation_message(
        conversation_id: str,
        user_id: str,
    ) -> None:
        """回答对话消息"""
        try:
            message = GPTServer.db_ops.get_message_list(conversation_id)
            # 删除消息列表中的系统消息
            message.delete_system_message()

            logger.info(f"message: {message.get_messages()}")
            await GPTServer._send_to_user(
                user_id,
                MessageFormat.create_conversation_message_response(
                    conversation_id,
                    message
                )
            )

            
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise 



    @staticmethod
    async def answer_question(
        question: str,
        user_id: str,
        conversation_id: str,
        mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """回答问题"""
        try:
            message_id = str(uuid.uuid4())
            user_message = Message(
                message_id=message_id,
                role="user",
                content=question,
                created_time=datetime.now()
            )
            GPTServer.db_ops.create_message(user_message, conversation_id)

            message = GPTServer.db_ops.get_message_list(conversation_id)

            logger.info(f"message: {message.get_messages()}")
            
            await GPTServer._answer_question(message, user_id, mcp_server_list, conversation_id)
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    @staticmethod
    async def _answer_question(
        messages: Messages,
        user_id: str,
        mcp_servers: Optional[MCPServers] = None,
        conversation_id: str = None
    ) -> None:
        """内部方法：处理问题回答"""
        try:
            available_functions = {}
            tools = []
            
            if mcp_servers:
                for mcp_server in mcp_servers.get_servers():
                    tools.extend(mcp_server["server_functions"])
                    for server_function in mcp_server["server_functions"]:
                        available_functions[server_function["function"]["name"]] = mcp_server["server_address"]

            chat_stream = GPTServer.model.chat_stream(messages=messages, tools=tools, temperature=0)
            function_calls = []
            full_response = ""

            for chunk in chat_stream:
                delta = chunk.choices[0].delta
                
                if delta.content is not None:
                    full_response += delta.content
                    await GPTServer._send_to_user(
                        user_id,
                        MessageFormat.create_answer_response(delta.content)
                    )
                
                if delta.tool_calls is not None:
                    if delta.tool_calls[0].id is not None:
                        function_calls.append({
                            "id": delta.tool_calls[0].id,
                            "name": delta.tool_calls[0].function.name,
                            "parameters": delta.tool_calls[0].function.arguments,
                            "server_address": available_functions[delta.tool_calls[0].function.name]
                        })
                    else:
                        function_calls[-1]["parameters"] += delta.tool_calls[0].function.arguments

            if function_calls:
                await GPTServer._send_to_user(
                    user_id,
                    MessageFormat.create_tool_selection_response(function_calls)
                )
            else:
                # 记录助手消息
                assistant_message = Message(
                    message_id=str(uuid.uuid4()),
                    role="assistant",
                    content=full_response,
                    created_time=datetime.now(),
                    tool_calls=None,
                    tool_call_id=None
                )
                GPTServer.db_ops.create_message(assistant_message, conversation_id)
                
        except Exception as e:
            error_msg = f"服务器处理GPT回答时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise MessageProcessingError(error_msg, ErrorCode.MSG_GPT_RESPONSE_ERROR)

    @staticmethod
    async def handle_heartbeat_failure(websocket: ServerConnection, user_id: str) -> None:
        """处理心跳失败"""
        logger.warning(f"用户 {user_id} 心跳失败，连接将被关闭")
        await GPTServer.remove_connection(user_id)
        await websocket.close(code=1000, reason="心跳超时")


    @staticmethod
    async def handle_auth(websocket: ServerConnection, auth_data: dict):
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
                
            user = GPTServer.db_ops.get_user_by_username(username)
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

    @staticmethod
    async def handle_register(register_data: dict) -> tuple[bool, dict]:
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

    @staticmethod
    async def handler(websocket: ServerConnection) -> None:
        """处理WebSocket连接"""
        user_id = None
        heartbeat_manager = None
        heartbeat_task = None

        try:
            # 等待认证消息
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
            logger.info(f"获取到认证消息: {auth_msg}")
            
            try:
                auth_data = json.loads(auth_msg)
                user = await GPTServer.handle_auth(websocket, auth_data)
                user_id = user.user_id
                
                # 获取用户的对话记录并发送
                conversations = GPTServer.db_ops.get_user_conversations(user_id)
                logger.info(f"获取到用户 {user_id} 的对话记录: {conversations}")
                if conversations:
                    await websocket.send(
                        MessageFormat.create_conversation_list_response(
                            conversations
                        )
                    )
                user_settings = GPTServer.db_ops.get_user_settings(user_id)
                logger.info(f"获取到用户 {user_id} 的服务器设置: {user_settings}")
                if user_settings:
                    await websocket.send(
                        MessageFormat.create_user_settings_response(
                            user_settings
                        )
                    )
                
            except AuthenticationError as e:
                logger.error(f"认证错误: {str(e)}", exc_info=True)
                await websocket.send(MessageFormat.create_error_response(
                    str(e),
                    e.error_code.value
                ))
                await websocket.close(code=1008, reason=str(e))
                return
            except json.JSONDecodeError as e:
                logger.error(f"认证消息格式错误: {str(e)}", exc_info=True)
                await websocket.send(MessageFormat.create_error_response(
                    "认证消息格式错误",
                    ErrorCode.AUTH_INVALID_FORMAT.value
                ))
                await websocket.close(code=1008, reason="认证消息格式错误")
                return

            # 创建心跳管理器
            heartbeat_manager = HeartbeatManager(
                websocket=websocket,
                user_id=user_id,
                interval=GPTServer.config.heartbeat_interval,
                timeout=GPTServer.config.heartbeat_timeout
            )
            heartbeat_task = asyncio.create_task(heartbeat_manager.start())
            
            # 注册连接到连接池
            await GPTServer.add_connection(user_id, websocket)

            # 主消息循环
            async for message in websocket:
                try:
                    if heartbeat_manager.handle_message(message):
                        continue
                    
                    websocket_message = WebsocketMessage(message)
                    message_type = websocket_message.get_type()
                    logger.info('message_type: %s', message_type)
                    
                    if message_type == "logout":
                        # 发送退出成功消息
                        await websocket.send(
                            MessageFormat.create_logout_success_response()
                        )
                    elif message_type == MessageFormat.RequestType.SETTINGS_ADD_SERVER.value:
                        await GPTServer.settings_user_server(
                            websocket_message.get_server(),
                            user_id
                        )
                    elif message_type == MessageFormat.RequestType.CONVERSATION_QUESTION.value:
                        await GPTServer.answer_conversation_question(
                            websocket_message.get_question(),
                            user_id,
                            websocket_message.get_mcp_servers()
                        )
                    elif message_type == MessageFormat.RequestType.CONVERSATION_MESSAGE.value:
                        await GPTServer.answer_conversation_message(
                            websocket_message.get_conversation_id(),
                            user_id
                        )
                    elif message_type == MessageFormat.RequestType.QUESTION.value:
                        await GPTServer.answer_question(
                            websocket_message.get_question(),
                            user_id,
                            websocket_message.get_conversation_id(),
                            websocket_message.get_mcp_servers(),
                        )
                    elif message_type == MessageFormat.RequestType.EXECUTE_TOOLS.value:
                        await GPTServer.answer_question_with_tools(
                            websocket_message.get_question(),
                            user_id,
                            websocket_message.get_conversation_id(),
                            websocket_message.get_select_functions(),
                            websocket_message.get_mcp_servers()
                        )
                    else:
                        error_msg = f"未知消息类型: {message_type}"
                        logger.warning(error_msg)
                        await websocket.send(MessageFormat.create_error_response(
                            error_msg,
                            ErrorCode.MSG_INVALID_TYPE.value
                        ))
                        
                except json.JSONDecodeError as e:
                    error_msg = f"JSON解析错误: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    await websocket.send(MessageFormat.create_error_response(
                        error_msg,
                        ErrorCode.MSG_JSON_PARSE_ERROR.value
                    ))
                except MessageProcessingError as e:
                    error_msg = f"消息处理错误: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    await websocket.send(MessageFormat.create_error_response(
                        error_msg,
                        e.error_code.value
                    ))
                except ToolExecutionError as e:
                    error_msg = f"工具执行错误: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    await websocket.send(MessageFormat.create_error_response(
                        error_msg,
                        e.error_code.value
                    ))
                except Exception as e:
                    error_msg = f"未知错误: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    await websocket.send(MessageFormat.create_error_response(
                        error_msg,
                        ErrorCode.SERVER_INTERNAL_ERROR.value
                    ))

        except asyncio.TimeoutError:
            logger.error("认证超时")
            await websocket.send(MessageFormat.create_error_response(
                "认证超时",
                ErrorCode.AUTH_TIMEOUT.value
            ))
            await websocket.close(code=1008, reason="认证超时")
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"用户 {user_id} 连接丢失")
            await websocket.send(MessageFormat.create_error_response(
                "连接已关闭",
                ErrorCode.SERVER_CONNECTION_ERROR.value
            ))
        except Exception as e:
            logger.error(f"处理连接时发生错误: {str(e)}", exc_info=True)
            await websocket.send(MessageFormat.create_error_response(
                "服务器内部错误",
                ErrorCode.SERVER_INTERNAL_ERROR.value
            ))
            await websocket.close(code=1011, reason="服务器内部错误")
        finally:
            if heartbeat_manager:
                heartbeat_manager.stop()
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if user_id:
                await GPTServer.remove_connection(user_id)

async def start_server(handler):
    config = GPTConfig()
    
    # 启动 WebSocket 服务器
    ws_server = await serve(handler, config.server_host, config.server_port)
    logger.info(f"WebSocket服务器启动在 {config.server_host}:{config.server_port}")
    
    # 启动 HTTP 服务器
    from src.GPTServer.HTTPServer import app
    import uvicorn
    import threading
    
    def run_http_server():
        uvicorn.run(app, host="localhost", port=8080)
    
    # 在新线程中启动 HTTP 服务器
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True  # 设置为守护线程，这样主程序退出时会自动结束
    http_thread.start()
    
    try:
        # 保持服务运行
        await asyncio.Future()
    except asyncio.CancelledError:
        # 清理资源
        ws_server.close()
        await ws_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(start_server(GPTServer.handler))

