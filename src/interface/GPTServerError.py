from .ErrorCode import ErrorCode

class GPTServerError(Exception):
    """GPT服务器基础异常类"""
    def __init__(self, message: str, error_code: ErrorCode):
        super().__init__(message)
        self.error_code = error_code

class AuthenticationError(GPTServerError):
    """认证相关异常"""
    def __init__(self, message: str, error_code: ErrorCode):
        super().__init__(message, error_code)

class MessageProcessingError(GPTServerError):
    """消息处理相关异常"""
    def __init__(self, message: str, error_code: ErrorCode):
        super().__init__(message, error_code)

class ToolExecutionError(GPTServerError):
    """工具执行相关异常"""
    def __init__(self, message: str, error_code: ErrorCode):
        super().__init__(message, error_code) 