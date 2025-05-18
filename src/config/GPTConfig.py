import os
from src.interface.EnumModel import EnumModel

class GPTConfig:
    """GPT服务器配置类"""
    def __init__(self):
        self.base_url = os.getenv("GPT_BASE_URL", "https://api.chatfire.cn/v1")
        self.api_key = os.getenv("GPT_API_KEY", "sk-JC1mYx4Wx0L7zf2ZD3qZWPM8YQH5ngz0h4CyNezNqw0qnJsX")
        self.model = os.getenv("GPT_MODEL", EnumModel.gpt_4o_mini)
        self.heartbeat_timeout = int(os.getenv("HEARTBEAT_TIMEOUT", 10))
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", 5))
        self.server_host = os.getenv("SERVER_HOST", "localhost")
        self.server_port = int(os.getenv("SERVER_PORT", 8765))
        self.http_host = os.getenv("HTTP_HOST", "localhost")
        self.http_port = int(os.getenv("HTTP_PORT", 8080))
        self.db_host = os.getenv("DB_HOST", "127.0.0.1")
        self.db_port = int(os.getenv("DB_PORT", 3306))
        self.db_user = os.getenv("DB_USER", "root")
        self.db_password = os.getenv("DB_PASSWORD", "123456")
        self.db_name = os.getenv("DB_NAME", "test")
        