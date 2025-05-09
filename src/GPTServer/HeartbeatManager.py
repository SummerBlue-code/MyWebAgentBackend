import asyncio
import websockets
import json
import logging
from typing import Optional
from src.interface.MessageFormat import MessageFormat
from src.interface.ErrorCode import ErrorCode

logger = logging.getLogger(__name__)

class HeartbeatManager:
    def __init__(
        self,
        websocket,
        user_id: str,
        interval: int = 25,
        timeout: int = 10,
        max_retries: int = 3
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.interval = interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_count = 0
        self.is_running = True
        self.last_heartbeat_time: Optional[float] = None
        self.heartbeat_received = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def handle_heartbeat_failure(self) -> None:
        """处理心跳失败"""
        logger.warning(f"用户 {self.user_id} 心跳失败，连接将被关闭")
        await self.websocket.close(code=1000, reason="心跳超时")

    async def send_heartbeat(self) -> None:
        """发送心跳消息"""
        try:
            timestamp = asyncio.get_event_loop().time()
            await self.websocket.send(MessageFormat.create_heartbeat_message(self.user_id, timestamp))
            self.last_heartbeat_time = timestamp
            self.heartbeat_received = False
            logger.debug(f"发送心跳消息给用户 {self.user_id}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"发送心跳消息时连接已关闭: {self.user_id}")
            await self.websocket.send(MessageFormat.create_error_response(
                "连接已关闭",
                ErrorCode.SERVER_CONNECTION_ERROR.value
            ))
            self.is_running = False
        except Exception as e:
            logger.error(f"发送心跳消息失败: {str(e)}", exc_info=True)
            await self.websocket.send(MessageFormat.create_error_response(
                "心跳消息发送失败",
                ErrorCode.SERVER_INTERNAL_ERROR.value
            ))
            self.is_running = False

    def handle_message(self, message: str) -> bool:
        """处理接收到的消息"""
        if MessageFormat.is_heartbeat_ack_message(message):
            self.heartbeat_received = True
            self.retry_count = 0
            logger.debug(f"收到用户 {self.user_id} 的心跳响应")
            return True
        return False

    async def _wait_for_heartbeat_ack(self) -> None:
        """等待心跳响应"""
        start_time = asyncio.get_event_loop().time()
        while not self.heartbeat_received and self.is_running:
            if asyncio.get_event_loop().time() - start_time > self.timeout:
                raise asyncio.TimeoutError()
            await asyncio.sleep(0.1)

    async def start(self) -> None:
        """启动心跳检测"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self._heartbeat_task

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while self.is_running and self.retry_count < self.max_retries:
            try:
                await asyncio.sleep(self.interval)
                await self.send_heartbeat()
                await self._wait_for_heartbeat_ack()
            except asyncio.TimeoutError:
                self.retry_count += 1
                logger.warning(f"用户 {self.user_id} 心跳超时，第 {self.retry_count} 次")
                await self.websocket.send(MessageFormat.create_error_response(
                    "心跳超时",
                    ErrorCode.HEARTBEAT_TIMEOUT.value
                ))
                if self.retry_count >= self.max_retries:
                    logger.error(f"用户 {self.user_id} 心跳失败，达到最大重试次数")
                    await self.websocket.send(MessageFormat.create_error_response(
                        "心跳失败，达到最大重试次数",
                        ErrorCode.HEARTBEAT_MAX_RETRIES.value
                    ))
                    self.is_running = False
                    await self.handle_heartbeat_failure()
                    break
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"用户 {self.user_id} 连接已关闭")
                await self.websocket.send(MessageFormat.create_error_response(
                    "连接已关闭",
                    ErrorCode.SERVER_CONNECTION_ERROR.value
                ))
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"心跳检测发生错误: {str(e)}", exc_info=True)
                await self.websocket.send(MessageFormat.create_error_response(
                    "心跳检测发生错误",
                    ErrorCode.SERVER_INTERNAL_ERROR.value
                ))
                self.is_running = False
                break

    def stop(self) -> None:
        """停止心跳检测"""
        self.is_running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            logger.info(f"停止用户 {self.user_id} 的心跳检测") 