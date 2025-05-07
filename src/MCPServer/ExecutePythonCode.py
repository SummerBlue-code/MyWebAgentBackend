import ast
import re
import logging
from contextlib import redirect_stdout
from io import StringIO
from time import time
from typing import Optional, List

from fastapi import FastAPI, Request, Response
from jsonrpcserver import Result, Success, dispatch, method
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def validate_code(code: str) -> Optional[dict]:
    """检查python代码的规范性"""
    # 检查print语句存在性
    if "print(" not in code:
        return {"error": "缺少print输出语句"}

    # 检查裸表达式（如直接写2+3）
    forbidden_patterns = [
        r"^\d+[\+\-\*/]",
        r";\s*\d+[\+\-\*/]"
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, code):
            return {"error": "检测到未封装表达式"}
    return None

def execute_python_code(code: str, timeout: int = 10, allowed_modules: Optional[List[str]] = None) -> dict:
    """执行Python代码"""
    # 初始化安全环境
    allowed_modules = allowed_modules or ["math", "datetime", "json"]
    restricted_globals = {"__builtins__": __builtins__}

    invalid_message = validate_code(code)
    if invalid_message:
        return invalid_message

    # 静态分析导入模块
    try:
        tree = ast.parse(code)
        imports = [n.names[0].name for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        forbidden = [imp for imp in imports if imp.split(".")[0] not in allowed_modules]
        if forbidden:
            return {"error": f"禁止导入模块: {', '.join(forbidden)}"}
    except Exception as e:
        return {"error": f"代码解析错误: {str(e)}"}

    # 执行环境配置
    output_buffer = StringIO()
    start_time = time()

    try:
        with redirect_stdout(output_buffer):
            exec(code, restricted_globals)
        result = output_buffer.getvalue().strip()
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return {
            "output": "",
            "error": error_msg,
            "execution_time": round(time() - start_time, 2)
        }

    return {
        "output": result,
        "error": "",
        "execution_time": round(time() - start_time, 2)
    }

@method(name='execute_python_code')
def _execute_python_code(code: str, timeout: int = 10, allowed_modules: Optional[List[str]] = None) -> Result:
    """JSON-RPC方法：执行Python代码"""
    response = execute_python_code(code, timeout, allowed_modules)
    logger.debug(response)
    return Success(response)

@app.post("/")
async def index(request: Request) -> Response:
    """处理JSON-RPC请求"""
    return Response(dispatch(await request.body()))

@app.get("/tools")
def tools() -> dict:
    """返回可用的工具函数信息"""
    functions_info = {
        "server_name": "ExecutePythonCode API",
        "version": "1.0",
        "available_functions": [
            {
                "type": "function",
                "function": {
                    "name": "execute_python_code",
                    "description": "执行Python代码并返回执行结果。该函数会执行输入的Python代码，并捕获代码在控制台的所有打印输出。代码执行过程中如果发生错误，会返回错误信息。",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "要执行的Python代码字符串。代码必须包含print语句来输出结果。"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "代码执行的最大时间限制（秒）。如果代码执行时间超过这个限制，将抛出超时异常。",
                                "default": 10
                            },
                            "allowed_modules": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "允许导入的Python模块列表。如果代码尝试导入未在此列表中指定的模块，将返回错误。默认允许导入math、datetime和json模块。",
                                "default": ["math", "datetime", "json"]
                            }
                        },
                        "required": ["code"],
                        "additionalProperties": False
                    },
                    "returns": {
                        "type": "object",
                        "properties": {
                            "output": {
                                "type": "string",
                                "description": "代码执行后在控制台打印的所有输出内容。"
                            },
                            "error": {
                                "type": "string",
                                "description": "如果执行过程中发生错误，这里会包含错误信息。如果执行成功则为空字符串。"
                            },
                            "execution_time": {
                                "type": "number",
                                "description": "代码执行所花费的时间（秒）。"
                            }
                        }
                    }
                }
            }
        ]
    }
    return functions_info

if __name__ == "__main__":
    logger.info("正在启动 ExecutePythonCode 服务器...")
    try:
        uvicorn.run(app, host="localhost", port=8002)
    except Exception as e:
        logger.error("服务器启动失败, 失败原因如下: %s", e) 