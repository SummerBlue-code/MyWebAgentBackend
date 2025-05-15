import logging
import json
from typing import Optional, Dict, Any
import requests

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

# 博查API配置
BOCHA_SEARCH_API = "https://api.bochaai.com/v1/web-search"
API_KEY: Optional[str] = None

def init_bocha(api_key: str):
    global API_KEY
    API_KEY = api_key

def bocha_search(
        query: str,
        summary: bool = True,
        count: int = 10,
        timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    try:
        if not API_KEY:
            raise Exception("API key not set. Please initialize with valid API key first.")

        logger.info("===== 正在请求博查的Search API. =====")
        payload = json.dumps({
            "query": query,
            "summary": summary,
            "count": count
        }, indent = 2, sort_keys = True)
        headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }
        logger.debug(f"===== 请求体为: =====\n{payload}")
        logger.debug(f"===== 请求头为: =====\n{json.dumps(headers, indent = 2, sort_keys = True)}")

        response = requests.request("POST", BOCHA_SEARCH_API, headers=headers, data=payload, timeout=timeout)

        # 强制检查HTTP状态码
        response.raise_for_status()

        # 尝试解析JSON（捕获解码错误）
        try:
            response_json = response.json()
            logger.info("===== 成功请求博查的Search API. =====")
            logger.debug(f"===== 响应体为: =====\n{json.dumps(response_json, indent = 2, sort_keys = True)}")
            return response_json
        except ValueError as e:
            logger.error(f"===== JSON解析失败: {str(e)} =====")
            return None

    except requests.exceptions.Timeout as e:
        logger.error(f"===== 请求超时: {str(e)} =====")
    except requests.exceptions.HTTPError as e:
        logger.error(f"===== HTTP错误 ({e.response.status_code}): {str(e)} =====")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"===== 连接错误: {str(e)} =====")
    except requests.exceptions.RequestException as e:
        logger.error(f"===== 请求异常: {str(e)} =====")
    except Exception as e:
        logger.error(f"===== 未知错误: {str(e)} =====", exc_info=True)

    return None

@method(name='web_search')
def web_search(query: str, summary: bool = True, count: int = 10) -> Dict[str, Any]:
    if not API_KEY:
        raise Exception("API key not set. Please initialize with valid API key first.")
    
    result = bocha_search(query=query, summary=summary, count=count)
    if result is None:
        raise Exception("Search request failed")
    return Success(result)

@app.post("/")
async def index(request: Request):
    return Response(dispatch(await request.body()))

@app.get("/tools")
def tools():
    functions_info = {
        "server_name": "BoChaServer API",
        "version": "1.0",
        "available_functions": [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "使用博查API进行网络搜索",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询字符串"
                            },
                            "summary": {
                                "type": "boolean",
                                "description": "是否返回摘要",
                                "default": True
                            },
                            "count": {
                                "type": "integer",
                                "description": "返回结果数量",
                                "default": 10
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False
                    }
                }
            }
        ]
    }
    return functions_info

def run_server(api_key: str):
    logger.info("正在启动 BoChaServer 服务器...")
    try:
        init_bocha(api_key)
        uvicorn.run(app, host="localhost", port=8003)
    except Exception as e:
        logger.error("服务器启动失败, 失败原因如下: %s", e)

if __name__ == "__main__":
    # 在实际使用时需要提供有效的 API key
    API_KEY = "sk-3a7510a045694c9582b9c69414ce0b19"
    run_server(API_KEY)