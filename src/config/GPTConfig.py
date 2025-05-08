import os
from src.interface.EnumModel import EnumModel

class GPTConfig:
    """GPT服务器配置类"""
    def __init__(self):
        self.base_url = os.getenv("GPT_BASE_URL", "https://api.moleapi.com/v1")
        self.api_key = os.getenv("GPT_API_KEY", "sk-RpraSr9gpvNxiNX7Al68OpmAEKnPqPppiLGX3j3ypgAIjnyf")
        self.model = os.getenv("GPT_MODEL", EnumModel.gpt_4o_mini)
        self.heartbeat_timeout = int(os.getenv("HEARTBEAT_TIMEOUT", 10))
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", 5))
        self.server_host = os.getenv("SERVER_HOST", "localhost")
        self.server_port = int(os.getenv("SERVER_PORT", 8765))
        self.db_host = "127.0.0.1"
        self.db_port = 3306
        self.db_user = "root"
        self.db_password = "123456"
        self.db_name = "ai agent"
        