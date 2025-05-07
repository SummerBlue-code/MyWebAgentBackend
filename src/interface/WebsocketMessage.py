import json
import logging

from src.interface.MCPServers import MCPServers

logger = logging.getLogger(__name__)

class WebsocketMessage:
    # 用户登录
    # 登录信息：{"user_id":"gg"}
    #
    #
    # 无工具提问
    # 用户提问：{"type": "user_question", "question": "杭州天气和交通情况"}
    #
    # 服务选择请求：
    # {
    #   "type": "server_answer",
    #   "answer": "今天多云"
    # }
    #

    # 有工具提问
    # 用户提问：{"type": "question", "question": "杭州天气和交通情况",
    # "mcp_servers":
    #   [
    #    {
    #      'server_name': server_name,
    #      'server_address': server_address,
    #      'server_functions': [
    #       {
    #             "type": "function",
    #             "function": {
    #                 "name": "get_current_weather",
    #                 "description": "Get the current weather in a given location",
    #                 "parameters": {
    #                     "type": "object",
    #                     "properties": {
    #                         "location": {
    #                             "type": "string",
    #                             "description": "The city and state, e.g. San Francisco, CA",
    #                         },
    #                         "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    #                     },
    #                     "required": ["location"],
    #                 },
    #             },
    #         }
    #      ],
    #    }
    #   ]
    # }
    #
    # # 服务选择请求：
    # {
    #   "type": "server_select_function",
    #   "select_functions": [{
    #     "id": "call_RzfkBpJgzeR0S242qfvjadNe",
    #     "function": {
    #         "name": "get_weather",
    #         "arguments": "{\"location\":\"Paris, France\"}"
    #     }
    #   }]
    # }
    #
    # 用户选择响应：
    # {
    #   "type": "user_select_function",
    #   "select_functions": [{
    #     "id": "call_RzfkBpJgzeR0S242qfvjadNe",
    #     "function": {
    #         "name": "get_weather",
    #         "arguments": "{\"location\":\"Paris, France\"}"
    #     }
    #   }]
    # }
    #
    # 服务选择请求：
    # {
    #   "type": "server_answer",
    #   "answer": "今天多云"
    # }
    #
    message = None

    def __init__(self, message):
        try:
            self.message = json.loads(message)
            logger.info(f"当前WebSocketMessage:{self.message}")
        except Exception as e:
            logger.error("WebSocketMessage转化失败")
            logger.error(f"失败原因如下:{e}")
            raise e

    def get_user_id(self):
        if self.message is not None:
            try:
                result = self.message["user_id"]
                logger.info("成功获取user_id")
                return result
            except KeyError:
                logger.warning("用户的Json格式不包含'user_id'属性")
                raise KeyError

    def get_type(self):
        if self.message is not None:
            try:
                return self.message["type"]
            except KeyError:
                logger.warning("用户的Json格式不包含'type'属性")
                raise KeyError

    def get_question(self):
        if self.message is not None:
            try:
                return self.message["question"]
            except KeyError:
                logger.warning("用户的Json格式不包含'question'属性")
                raise KeyError

    def get_mcp_servers(self):
        if self.message is not None:
            try:
                return MCPServers(self.message["mcp_servers"])
            except KeyError:
                logger.warning("用户的Json格式不包含'mcp_servers'属性,已使用默认值:[]")
                return MCPServers()

    def get_select_functions(self):
        if self.message is not None:
            try:
                return self.message["select_functions"]
            except KeyError:
                logger.warning("用户的Json格式不包含'select_functions'属性")
                raise KeyError