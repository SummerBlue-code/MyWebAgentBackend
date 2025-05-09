import asyncio
import logging
import signal
import sys
import multiprocessing
from typing import List, Optional

from src.GPTServer.GPTServer import GPTServer, start_server
from src.GPTServer.HTTPServer import start_http_server
from src.MCPServer.Time import run_server as run_time_server
from src.MCPServer.ExecutePythonCode import run_server as run_python_server

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_websocket_server():
    """运行WebSocket服务器"""
    try:
        # 启动服务器
        asyncio.run(start_server(GPTServer.handler))
    except Exception as e:
        logger.error(f"WebSocket服务器启动失败: {str(e)}")

def run_http_server():
    """运行HTTP服务器"""
    try:
        start_http_server()
    except Exception as e:
        logger.error(f"HTTP服务器启动失败: {str(e)}")

def run_time_server_process():
    """运行时间服务器"""
    try:
        run_time_server()
    except Exception as e:
        logger.error(f"时间服务器启动失败: {str(e)}")

def run_python_server_process():
    """运行Python代码执行服务器"""
    try:
        run_python_server()
    except Exception as e:
        logger.error(f"Python代码执行服务器启动失败: {str(e)}")

def main():
    """主函数"""
    # 创建进程列表
    processes = []
    
    try:
        # 启动WebSocket服务器
        ws_process = multiprocessing.Process(target=run_websocket_server)
        ws_process.start()
        processes.append(ws_process)
        logger.info("WebSocket服务器启动成功")
        
        # 启动HTTP服务器
        http_process = multiprocessing.Process(target=run_http_server)
        http_process.start()
        processes.append(http_process)
        logger.info("HTTP服务器启动成功")
        
        # 启动时间服务器
        time_process = multiprocessing.Process(target=run_time_server_process)
        time_process.start()
        processes.append(time_process)
        logger.info("时间服务器启动成功")
        
        # 启动Python代码执行服务器
        python_process = multiprocessing.Process(target=run_python_server_process)
        python_process.start()
        processes.append(python_process)
        logger.info("Python代码执行服务器启动成功")
        
        # 等待所有进程
        for process in processes:
            process.join()
            
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭所有服务器...")
    except Exception as e:
        logger.error(f"服务器运行出错: {str(e)}")
    finally:
        # 关闭所有进程
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
        logger.info("所有服务器已关闭")

if __name__ == "__main__":
    # 设置多进程启动方法
    multiprocessing.set_start_method('spawn')
    
    try:
        main()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序发生错误: {str(e)}")
        sys.exit(1)
