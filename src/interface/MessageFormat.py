import json
from enum import Enum
from typing import Dict, List, Any, TypedDict

class MessageFormat:
    """消息格式统一管理类"""
    
    class RequestType(Enum):
        """请求类型枚举"""
        QUESTION = "user_question"
        EXECUTE_TOOLS = "execute_tools"
        HEARTBEAT = "heartbeat"
    
    class ResponseType(Enum):
        """响应类型枚举"""
        ANSWER = "server_answer"
        SELECT_TOOLS = "server_select_function"
        HEARTBEAT_ACK = "heartbeat_ack"
        ERROR = "error"
    
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
    
    @staticmethod
    def _create_json_message(message_type: str, **kwargs) -> str:
        """创建JSON消息的通用方法"""
        result = {"type": message_type, **kwargs}
        return json.dumps(result, ensure_ascii=False)
    
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