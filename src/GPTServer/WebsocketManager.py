import logging
import asyncio
from typing import Dict, Optional, Set
from asyncio import Lock, Queue
from concurrent.futures import ThreadPoolExecutor
from websockets import ServerConnection

logger = logging.getLogger(__name__)

class WebsocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        """初始化WebSocket管理器"""
        self._active_connections: Dict[str, ServerConnection] = {}  # 连接池：{user_id: websocket}
        self._connection_lock: Lock = Lock()  # 连接池锁
        self._active_workers: Set[str] = set()  # 活跃的工作任务
        self._worker_lock: Lock = Lock()  # 工作任务锁
        # 线程池配置
        self._thread_pool = ThreadPoolExecutor(max_workers=10)  # 最多10个线程
        # 流控制参数
        self._send_interval = 0.05  # 消息之间的发送间隔(秒)，20条/秒
    
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
    
    async def _send_message(self, websocket: ServerConnection, message: str) -> None:
        """发送单条消息的异步方法
        
        Args:
            websocket (ServerConnection): WebSocket连接
            message (str): 消息内容
        """
        try:
            await websocket.send(message)
            await asyncio.sleep(self._send_interval)  # 控制发送速率
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
            raise
    
    async def send_to_user(self, target_user_id: str, message: str, priority: bool = False) -> None:
        """向指定用户发送消息（使用线程池并发发送）
        
        Args:
            target_user_id (str): 目标用户ID
            message (str): 消息内容
            priority (bool): 是否为优先消息（在线程池实现中暂不支持）
        """
        # 检查用户是否在线
        websocket = await self.get_connection(target_user_id)
        if not websocket:
            logger.warning(f"用户 {target_user_id} 不在线，无法发送消息")
            return
        
        try:
            # 使用线程池提交发送任务
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._thread_pool,
                lambda: asyncio.run_coroutine_threadsafe(
                    self._send_message(websocket, message),
                    loop
                )
            )
            logger.debug(f"消息已提交到线程池发送给用户 {target_user_id}")
        except Exception as e:
            logger.error(f"向用户 {target_user_id} 发送消息失败: {str(e)}")
    
    def set_send_rate(self, messages_per_second: int) -> None:
        """设置每秒发送消息的数量限制
        
        Args:
            messages_per_second (int): 每秒消息数量
        """
        if messages_per_second <= 0:
            messages_per_second = 20  # 默认值
        self._send_interval = 1.0 / messages_per_second
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，确保资源正确释放"""
        self._thread_pool.shutdown(wait=True) 