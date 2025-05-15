import asyncio
import json
import logging
from typing import Optional, List
from datetime import datetime
import uuid

import httpx
from websockets import ServerConnection

from src.interface import Messages
from src.interface.MCPServers import MCPServers
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import GPTServerError, ToolExecutionError, MessageProcessingError
from src.database.models import User, Conversation, Message
from src.database.operations import DatabaseOperations
from src.models.GPTModel import GPTModel

logger = logging.getLogger(__name__)

class ConversationManager:
    """对话管理器，处理对话相关的操作"""
    
    def __init__(self, db_ops, model, websocket_manager, gpt_server):
        """初始化对话管理器
        
        Args:
            db_ops: 数据库操作实例
            model: GPT模型实例
            websocket_manager: WebSocket管理器实例
            system_prompts: 系统提示词
        """
        self.db_ops = db_ops
        self.model = model
        self.websocket_manager = websocket_manager
        self.gpt_server = gpt_server
        
    async def answer_question_with_tools(
        self,
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
            self.db_ops.create_message(assistant_tool_message, conversation_id)

            # 处理工具调用
            for select_tool in select_tools:
                await self._process_tool_result(select_tool, conversation_id)

            # 获取完整的消息历史
            message = self.db_ops.get_message_list(conversation_id)


            logger.info(f"处理工具调用后的消息历史: {message.get_messages()}")
            
            # 继续对话
            await self._answer_question(message, user_id, mcp_server_list, conversation_id)

        except Exception as e:
            logger.error(f"处理带工具的问题时出错: {str(e)}")
            raise

    async def get_conversation_title(self, question: str, user_id: str, conversation_id: str) -> str:
        """获取对话标题"""
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
        response = self.model.chat_stream(messages=messages, tools=[], temperature=0)
        full_response = ""

        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content is not None:
                full_response += chunk.choices[0].delta.content
                await self.websocket_manager.send_to_user(
                    user_id,
                    MessageFormat.create_conversation_title_response(
                        conversation_id,
                        chunk.choices[0].delta.content
                    )
                )
        return full_response

    async def answer_conversation_question(
        self,
        question: str,
        user_id: str,
        mcp_server_list: Optional[MCPServers] = None
    ) -> None:
        """回答对话问题"""
        try:
            conversation_id = str(uuid.uuid4())
            conversation = Conversation(
                conversation_id=conversation_id,
                title=await self.get_conversation_title(question, user_id, conversation_id),
                create_time=datetime.now(),
                update_time=datetime.now(),
                status="active"
            )
            self.db_ops.create_conversation(conversation, user_id)

            system_prompt = Message(
                message_id=str(uuid.uuid4()),
                role="system",
                content=self.gpt_server.system_prompts,
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=None
            )
            self.db_ops.create_message(system_prompt, conversation_id)
            
            user_message = Message(
                message_id=str(uuid.uuid4()),
                role="user",
                content=question,
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=None
            )
            self.db_ops.create_message(user_message, conversation_id)
            message = self.db_ops.get_conversation_messages(conversation_id)

            await self._answer_question(message, user_id, mcp_server_list, conversation_id)
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    async def answer_conversation_message(
        self,
        conversation_id: str,
        user_id: str,
    ) -> None:
        """回答对话消息"""
        try:
            message = self.db_ops.get_message_list(conversation_id)
            # 删除消息列表中的系统消息，并且只保留用户消息和内容不为空的助手消息
            message.delete_system_message()
            message.filter_valid_conversation_messages()

            logger.info(f"message: {message.get_messages()}")
            await self.websocket_manager.send_to_user(
                user_id,
                MessageFormat.create_conversation_message_response(
                    conversation_id,
                    message
                )
            )
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    async def answer_question(
        self,
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
                created_time=datetime.now(),
                tool_call_id=None,
                tool_calls=None
            )
            self.db_ops.create_message(user_message, conversation_id)

            message = self.db_ops.get_message_list(conversation_id)

            logger.info(f"message: {message.get_messages()}")
            
            await self._answer_question(message, user_id, mcp_server_list, conversation_id)
        except Exception as e:
            logger.error(f"处理问题时出错: {str(e)}")
            raise

    async def _process_tool_result(self, select_tool: dict, conversation_id: str) -> None:
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
                self.db_ops.create_message(tool_message, conversation_id)
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

    async def _answer_question(
        self,
        messages: Messages,
        user_id: str,
        mcp_servers: Optional[MCPServers] = None,
        conversation_id: str = None
    ) -> None:
        """内部方法：处理问题回答"""
        try:
            available_functions = {}
            tools = []
            if messages.get_messages()[0]["role"] == "system":
                messages.get_messages()[0]["content"] = self.gpt_server.system_prompts
            if mcp_servers:
                for mcp_server in mcp_servers.get_servers():
                    tools.extend(mcp_server["server_functions"])
                    for server_function in mcp_server["server_functions"]:
                        available_functions[server_function["function"]["name"]] = mcp_server["server_address"]

            chat_stream = self.model.chat_stream(messages=messages, tools=tools, temperature=0)
            function_calls = []
            full_response = ""

            for chunk in chat_stream:
                delta = chunk.choices[0].delta
                
                if delta.content is not None:
                    full_response += delta.content
                    await self.websocket_manager.send_to_user(
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
                await self.websocket_manager.send_to_user(
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
                self.db_ops.create_message(assistant_message, conversation_id)
                
        except Exception as e:
            error_msg = f"服务器处理GPT回答时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise MessageProcessingError(error_msg, ErrorCode.MSG_GPT_RESPONSE_ERROR)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        """删除对话
        
        Args:
            conversation_id (str): 对话ID
            user_id (str): 用户ID
            
        Raises:
            GPTServerError: 删除失败时抛出
        """
        try:
            # 检查对话是否存在
            conversation = self.db_ops.get_conversation(conversation_id)
            if not conversation:
                raise GPTServerError("对话不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 删除对话及其所有消息
            success = self.db_ops.delete_conversation(conversation_id)
            if not success:
                raise GPTServerError("删除对话失败", ErrorCode.SERVER_INTERNAL_ERROR)
                
            logger.info(f"成功删除对话 {conversation_id}")

            await self.websocket_manager.send_to_user(
                user_id,
                MessageFormat.create_delete_conversation_response(conversation_id)
            )
            
        except Exception as e:
            logger.error(f"删除对话失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"删除对话失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    async def get_conversation_list(self, user_id: str) -> None:
        """获取用户的对话列表
        
        Args:
            user_id (str): 用户ID
            
        Raises:
            GPTServerError: 获取失败时抛出
        """
        try:
            # 获取用户的对话列表
            conversations = self.db_ops.get_user_conversations(user_id)
            if conversations is None:
                raise GPTServerError("获取对话列表失败", ErrorCode.SERVER_INTERNAL_ERROR)
                
            logger.info(f"成功获取用户 {user_id} 的对话列表")
            
            # 发送对话列表给用户
            await self.websocket_manager.send_to_user(
                user_id,
                MessageFormat.create_conversation_list_response(conversations)
            )
            
        except Exception as e:
            logger.error(f"获取对话列表失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"获取对话列表失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR) 
        