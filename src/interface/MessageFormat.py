import json
from enum import Enum
from typing import Dict, List, Any, TypedDict

from src.database.models import Conversation
from src.interface import Messages


class MessageFormat:
    """消息格式统一管理类"""
    
    class RequestType(Enum):
        """请求类型枚举"""
        CONVERSATION_QUESTION = "conversation_question"
        CONVERSATION_MESSAGE = "conversation_message"
        QUESTION = "user_question"
        EXECUTE_TOOLS = "execute_tools"
        HEARTBEAT = "heartbeat"
        SETTINGS_ADD_SERVER = "settings_add_server"
        REGISTER = "register"
    
    class ResponseType(Enum):
        """响应类型枚举"""
        CONVERSATION_MESSAGE = "conversation_message"
        ANSWER = "server_answer"
        SELECT_TOOLS = "server_select_function"
        HEARTBEAT_ACK = "heartbeat_ack"
        ERROR = "error"
        CONVERSATION_TITLE = "conversation_title"
        CONVERSATION_LIST = "conversation_list"
        USER_SETTINGS = "user_settings"
        REGISTER_SUCCESS = "register_success"
        AUTH_SUCCESS = "auth_success"
        LOGOUT_SUCCESS = "logout_success"

    class AuthMessage(TypedDict):
        """认证消息格式"""
        user_id: str
    
    class QuestionRequest(TypedDict):
        """问题请求格式"""
        type: str
        question: str
    
    class ToolRequest(TypedDict):
        """工具执行请求格式"""
        type: str
        question: str
        select_functions: List[Dict[str, Any]]
    
    class AnswerResponse(TypedDict):
        """回答响应格式"""
        type: str
        answer: str
    
    class ToolSelectionResponse(TypedDict):
        """工具选择响应格式"""
        type: str
        select_functions: List[Dict[str, Any]]
    
    class JsonRpcRequest(TypedDict):
        """JSON-RPC请求格式"""
        jsonrpc: str
        method: str
        params: Dict[str, Any]
        id: str
    
    class HeartbeatMessage(TypedDict):
        """心跳消息格式"""
        type: str
        data: Dict[str, Any]
    
    class HeartbeatAckMessage(TypedDict):
        """心跳确认消息格式"""
        type: str
        data: Dict[str, Any]
    
    class ErrorResponse(TypedDict):
        """错误响应格式"""
        type: str
        code: int
        message: str
    
    class RegisterRequest(TypedDict):
        """注册请求格式"""
        type: str
        username: str
        password: str
    
    class RegisterResponse(TypedDict):
        """注册响应格式"""
        type: str
        user_id: str
        username: str
    
    @staticmethod
    def _create_json_message(message_type: str, **kwargs) -> str:
        """创建JSON消息的通用方法"""
        result = {"type": message_type, **kwargs}
        return json.dumps(result, ensure_ascii=False)
    
    @staticmethod
    def create_auth_success_response(user_id: str, username: str) -> str:
        """创建认证成功消息"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.AUTH_SUCCESS.value,
            user_id=user_id,
            username=username
        )
    @staticmethod
    def create_auth_message(user_id: str) -> str:
        """创建认证消息"""
        return json.dumps({"user_id": user_id}, ensure_ascii=False)
    
    @staticmethod
    def create_question_request(question: str) -> str:
        """创建问题请求"""
        return MessageFormat._create_json_message(MessageFormat.RequestType.QUESTION.value, question=question)
    
    @staticmethod
    def create_tool_request(question: str, select_functions: List[Dict[str, Any]]) -> str:
        """创建工具执行请求"""
        return MessageFormat._create_json_message(
            MessageFormat.RequestType.EXECUTE_TOOLS.value,
            question=question,
            select_functions=select_functions
        )
    
    @staticmethod
    def create_conversation_title_response(conversation_id: str, title: str) -> str:
        """创建对话标题请求"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.CONVERSATION_TITLE.value,
            conversation_id=conversation_id,
            title=title
        )

    @staticmethod
    def create_answer_response(answer: str) -> str:
        """创建回答响应"""
        return MessageFormat._create_json_message(MessageFormat.ResponseType.ANSWER.value, answer=answer)
    
    @staticmethod
    def create_tool_selection_response(select_functions: List[Dict[str, Any]]) -> str:
        """创建工具选择响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.SELECT_TOOLS.value,
            select_functions=select_functions
        )
    
    @staticmethod
    def create_json_rpc_request(id: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建JSON-RPC请求"""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": id
        }
    
    @staticmethod
    def create_heartbeat_message(user_id: str, timestamp: float) -> str:
        """创建心跳消息"""
        return MessageFormat._create_json_message(
            MessageFormat.RequestType.HEARTBEAT.value,
            data={
                "user_id": user_id,
                "timestamp": timestamp
            }
        )
    
    @staticmethod
    def create_heartbeat_ack_message(timestamp: float) -> str:
        """创建心跳确认消息"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.HEARTBEAT_ACK.value,
            data={
                "status": "ok",
                "timestamp": timestamp
            }
        )
    
    @staticmethod
    def create_conversation_list_response(conversations: List[Conversation]) -> str:
        """创建对话列表响应"""
        # 将Conversation对象转换为字典
        conversation_dicts = []
        for conv in conversations:
            conversation_dicts.append({
                "conversation_id": conv.conversation_id,
                "title": conv.title,
            })
            
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.CONVERSATION_LIST.value,
            conversations=conversation_dicts
        )
    
    @staticmethod
    def create_user_settings_response(user_settings: dict) -> str:
        """创建用户设置响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.USER_SETTINGS.value,
            user_settings=user_settings
        )

    @staticmethod
    def create_conversation_message_response(conversation_id: str, messages: Messages) -> str:
        """创建对话消息响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.CONVERSATION_MESSAGE.value,
            conversation_id=conversation_id,
            messages=messages.get_messages()
        )


    @staticmethod
    def create_error_response(error_message: str, error_code: int) -> str:
        """创建错误响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.ERROR.value,
            code=error_code,
            message=error_message
        )
    
    @staticmethod
    def is_heartbeat_message(message: str) -> bool:
        """判断是否为心跳消息"""
        try:
            data = json.loads(message)
            return data.get("type") == MessageFormat.RequestType.HEARTBEAT.value
        except json.JSONDecodeError:
            return False
    
    @staticmethod
    def is_heartbeat_ack_message(message: str) -> bool:
        """判断是否为心跳确认消息"""
        try:
            data = json.loads(message)
            return data.get("type") == MessageFormat.ResponseType.HEARTBEAT_ACK.value
        except json.JSONDecodeError:
            return False

    @staticmethod
    def create_register_response(user_id: str, username: str) -> str:
        """创建注册响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.REGISTER_SUCCESS.value,
            user_id=user_id,
            username=username
        )

    @staticmethod
    def create_logout_success_response() -> str:
        """创建退出成功响应"""
        return MessageFormat._create_json_message(
            MessageFormat.ResponseType.LOGOUT_SUCCESS.value,
            message="退出成功"
        )
