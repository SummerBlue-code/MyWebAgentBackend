import asyncio
import logging

import websockets
from websockets import serve, ServerConnection

from src.models.GPTModel import GPTModel
from src.GPTServer.HeartbeatManager import HeartbeatManager
from src.GPTServer.WebsocketManager import WebsocketManager
from src.GPTServer.ConversationManager import ConversationManager
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import GPTServerError, AuthenticationError, MessageProcessingError, ToolExecutionError
from src.config.GPTConfig import GPTConfig
from src.database.base import Database
from src.database.operations import DatabaseOperations
from src.database.models import User, Conversation, Message, ConversationMessage, ToolCall, MessageToolCall
from src.GPTServer.MessageHandler import MessageHandler
from src.GPTServer.AuthenticationHandler import AuthenticationHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GPTServer:
    """GPT服务器类，处理WebSocket连接和消息处理"""
    
    # 类属性
    websocket_manager = WebsocketManager()
    config = GPTConfig()
    
    # 数据库配置
    db = Database(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name
    )
    db_ops = DatabaseOperations(db)
    
    # GPT模型配置
    model: GPTModel = GPTModel(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model
    )
    
    system_prompts: str

    

    def __init__(self):
        """初始化GPTServer"""
        # 对话管理器
        self.conversation_manager = ConversationManager(
            db_ops=self.db_ops,
            model=self.model,
            websocket_manager=self.websocket_manager,
            gpt_server=self
        )

    @staticmethod
    async def handler(websocket: ServerConnection) -> None:
        """处理WebSocket连接"""
        user_id = None
        heartbeat_manager = None
        heartbeat_task = None
        gpt_server = GPTServer()  # 创建 GPTServer 实例
        message_handler = MessageHandler(gpt_server)
        auth_handler = AuthenticationHandler(GPTServer.db_ops)

        try:
            # 1. 处理认证
            user, user_id = await auth_handler.handle_authentication(websocket)
            
            # 2. 发送初始数据
            await message_handler.send_initial_data(websocket, user_id)
            
            # 3. 设置心跳管理
            heartbeat_manager = HeartbeatManager(
                websocket=websocket,
                user_id=user_id,
                interval=GPTServer.config.heartbeat_interval,
                timeout=GPTServer.config.heartbeat_timeout
            )
            heartbeat_task = asyncio.create_task(heartbeat_manager.start())
            
            # 4. 注册连接到连接池
            await GPTServer.websocket_manager.add_connection(user_id, websocket)

            # 5. 主消息循环
            async for message in websocket:
                try:
                    await message_handler.handle_message(websocket, message, user_id, heartbeat_manager)
                except Exception as e:
                    await message_handler.handle_message_error(websocket, e)

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
            # 6. 清理资源
            if heartbeat_manager:
                heartbeat_manager.stop()
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if user_id:
                await GPTServer.websocket_manager.remove_connection(user_id)

async def start_server(handler):
    config = GPTConfig()
    
    # 启动 WebSocket 服务器
    ws_server = await serve(handler, config.server_host, config.server_port)
    logger.info(f"WebSocket服务器启动在 {config.server_host}:{config.server_port}")
    
    try:
        # 保持服务运行
        await asyncio.Future()
    except asyncio.CancelledError:
        # 清理资源
        ws_server.close()
        await ws_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(start_server(GPTServer.handler))

