import logging
from typing import Dict, Optional
from asyncio import Lock
from websockets import ServerConnection

logger = logging.getLogger(__name__)

class WebsocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        """初始化WebSocket管理器"""
        self._active_connections: Dict[str, ServerConnection] = {}  # 连接池：{user_id: websocket}
        self._connection_lock: Lock = Lock()  # 连接池锁
    
    async def add_connection(self, user_id: str, websocket: ServerConnection) -> None:
        """添加连接
        
        Args:
            user_id (str): 用户ID
            websocket (ServerConnection): WebSocket连接
        """
        async with self._connection_lock:
            self._active_connections[user_id] = websocket
            logger.info(f"用户 {user_id} 已连接，当前在线用户数：{len(self._active_connections)}")
    
    async def remove_connection(self, user_id: str) -> None:
        """移除连接
        
        Args:
            user_id (str): 用户ID
        """
        async with self._connection_lock:
            if user_id in self._active_connections:
                del self._active_connections[user_id]
                logger.info(f"用户 {user_id} 已断开连接，当前在线用户数：{len(self._active_connections)}")
    
    async def get_connection(self, user_id: str) -> Optional[ServerConnection]:
        """获取连接
        
        Args:
            user_id (str): 用户ID
            
        Returns:
            Optional[ServerConnection]: WebSocket连接，如果不存在则返回None
        """
        async with self._connection_lock:
            return self._active_connections.get(user_id)
    
    async def send_to_user(self, target_user_id: str, message: str) -> None:
        """向指定用户发送消息
        
        Args:
            target_user_id (str): 目标用户ID
            message (str): 消息内容
        """
        websocket = await self.get_connection(target_user_id)
        if websocket:
            try:
                await websocket.send(message)
            except Exception as e:
                logger.warning(f"向用户 {target_user_id} 发送消息失败: {str(e)}")
                await self.remove_connection(target_user_id) 