import asyncio
import json
import logging
from typing import Optional, Dict, List, Any, TypedDict
from collections import defaultdict
from asyncio import Lock

import httpx
import websockets
from websockets import serve, ServerConnection

from src.interface import Messages
from src.interface.EnumModel import EnumModel
from src.interface.GPTModel import GPTModel
from src.interface.MCPServers import MCPServers
from src.interface.WebsocketMessage import WebsocketMessage
from src.interface.HeartbeatManager import HeartbeatManager
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import GPTServerError, AuthenticationError, MessageProcessingError, ToolExecutionError
from src.config.GPTConfig import GPTConfig

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
    async def _process_tool_result(select_tool: dict, message: Messages) -> None:
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
                
                message.add_tool_message(select_tool["id"], json.dumps(response_data["result"]))
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
        select_tools: List[dict],
        mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """使用工具回答问题"""
        try:
            message = Messages()
            message.add_system_message(GPTServer.system_prompts)
            message.add_user_message(question)
            
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
            
            message.add_assistant_tool_call_message(gpt_tool_calls)
            
            for select_tool in select_tools:
                await GPTServer._process_tool_result(select_tool, message)
            
            await GPTServer._answer_question(message, user_id, mcp_server_list)
        except Exception as e:
            logger.error(f"处理带工具的问题时出错: {str(e)}")
            raise

    @staticmethod
    async def answer_question(
        question: str,
        user_id: str,
        mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """回答问题"""
        try:
            message = Messages()
            message.add_system_message(GPTServer.system_prompts)
            message.add_user_message(question)
            await GPTServer._answer_question(message, user_id, mcp_server_list)
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    @staticmethod
    async def _answer_question(
        messages: Messages,
        user_id: str,
        mcp_servers: Optional[MCPServers] = None
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

            for chunk in chat_stream:
                delta = chunk.choices[0].delta
                
                if delta.content is not None:
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
                user_id = auth_data.get("user_id")
                if not user_id:
                    raise AuthenticationError("认证消息中缺少user_id", ErrorCode.AUTH_MISSING_USER_ID)
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
                    
                    if message_type == MessageFormat.RequestType.QUESTION.value:
                        await GPTServer.answer_question(
                            websocket_message.get_question(),
                            user_id,
                            websocket_message.get_mcp_servers(),
                        )
                    elif message_type == MessageFormat.RequestType.EXECUTE_TOOLS.value:
                        await GPTServer.answer_question_with_tools(
                            websocket_message.get_question(),
                            user_id,
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
    async with serve(handler, config.server_host, config.server_port):
        logger.info(f"服务器启动在 {config.server_host}:{config.server_port}")
        await asyncio.Future()  # 保持服务运行

if __name__ == "__main__":
    asyncio.run(start_server(GPTServer.handler))

