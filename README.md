# AI Agent 项目

这是一个基于 Python 的 AI 代理系统，集成了多个功能服务器，包括 GPT 服务、时间服务、Python 代码执行服务等。

## 功能特性

- WebSocket 服务器：提供实时通信功能
- HTTP 服务器：处理 HTTP 请求
- 时间服务器：提供时间相关服务
- Python 代码执行服务器：支持远程执行 Python 代码
- 博查服务器：集成 AI Web 查询功能

## 系统要求

- Python 3.8+
- MySQL 数据库

## 安装步骤

1. 克隆项目到本地：
```bash
git clone [项目地址]
cd AI-Agent
```

2. 创建并激活虚拟环境：
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

## 配置说明

1. 数据库配置：
   - 确保 MySQL 服务已启动
   - 在 `src/config/GPTConfig.py` 中配置数据库连接信息：
     ```python
     self.db_host = "127.0.0.1"  # 数据库主机地址
     self.db_port = 3306         # 数据库端口
     self.db_user = "root"       # 数据库用户名
     self.db_password = "123456" # 数据库密码
     self.db_name = "ai agent"   # 数据库名称
     ```

2. API 密钥配置：
   - 在 `src/config/GPTConfig.py` 中配置 GPT 相关参数：
     ```python
     self.base_url = "https://api.moleapi.com/v1"  # API 基础URL
     self.api_key = "your-api-key"                 # API密钥
     self.model = "gpt-4o-mini"                    # 使用的模型
     ```
   - 也可以通过环境变量配置：
     ```bash
     # Windows
     set GPT_BASE_URL=your-base-url
     set GPT_API_KEY=your-api-key
     set GPT_MODEL=your-model-name
     
     # Linux/Mac
     export GPT_BASE_URL=your-base-url
     export GPT_API_KEY=your-api-key
     export GPT_MODEL=your-model-name
     ```

3. 服务器配置：
   - 在 `src/config/GPTConfig.py` 中配置服务器参数：
     ```python
     self.server_host = "localhost"  # 服务器主机地址
     self.server_port = 8765        # 服务器端口
     self.heartbeat_timeout = 10    # 心跳超时时间（秒）
     self.heartbeat_interval = 5    # 心跳间隔时间（秒）
     ```
   - 同样支持通过环境变量配置：
     ```bash
     # Windows
     set SERVER_HOST=your-host
     set SERVER_PORT=your-port
     set HEARTBEAT_TIMEOUT=10
     set HEARTBEAT_INTERVAL=5
     
     # Linux/Mac
     export SERVER_HOST=your-host
     export SERVER_PORT=your-port
     export HEARTBEAT_TIMEOUT=10
     export HEARTBEAT_INTERVAL=5
     ```

4. 数据库结构：
   项目使用 MySQL 数据库，主要包含以下表结构：

   ```sql
   -- 用户表
   CREATE TABLE users (
       user_id VARCHAR(36) PRIMARY KEY,
       username VARCHAR(50) NOT NULL,
       password VARCHAR(255) NOT NULL,
       create_time DATETIME NOT NULL,
       settings TEXT
   );

   -- 对话表
   CREATE TABLE conversations (
       conversation_id VARCHAR(36) PRIMARY KEY,
       title VARCHAR(255),
       create_time DATETIME NOT NULL,
       update_time DATETIME NOT NULL,
       status VARCHAR(20) NOT NULL
   );

   -- 消息表
   CREATE TABLE messages (
       message_id VARCHAR(36) PRIMARY KEY,
       role VARCHAR(20) NOT NULL,
       content TEXT,
       created_time DATETIME NOT NULL,
       tool_call_id VARCHAR(36),
       tool_calls TEXT
   );

   -- 对话消息关联表
   CREATE TABLE conversation_messages (
       conversation_id VARCHAR(36),
       message_id VARCHAR(36),
       create_time DATETIME NOT NULL,
       PRIMARY KEY (conversation_id, message_id),
       FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id),
       FOREIGN KEY (message_id) REFERENCES messages(message_id)
   );

   -- 工具调用表
   CREATE TABLE tool_calls (
       call_id VARCHAR(36) PRIMARY KEY,
       tool_name VARCHAR(50) NOT NULL,
       tool_parameters JSON,
       status VARCHAR(20) NOT NULL,
       result JSON,
       create_time DATETIME NOT NULL
   );

   -- 消息工具调用关联表
   CREATE TABLE message_tool_calls (
       message_id VARCHAR(36),
       tool_call_id VARCHAR(36),
       create_time DATETIME NOT NULL,
       PRIMARY KEY (message_id, tool_call_id),
       FOREIGN KEY (message_id) REFERENCES messages(message_id),
       FOREIGN KEY (tool_call_id) REFERENCES tool_calls(call_id)
   );

   -- 用户对话关联表
   CREATE TABLE user_conversations (
       user_id VARCHAR(36),
       conversation_id VARCHAR(36),
       create_time DATETIME NOT NULL,
       PRIMARY KEY (user_id, conversation_id),
       FOREIGN KEY (user_id) REFERENCES users(user_id),
       FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
   );

   -- 知识库文件表
   CREATE TABLE knowledge_base_files (
       file_id VARCHAR(36) PRIMARY KEY,
       knowledge_base_id VARCHAR(36) NOT NULL,
       file_name VARCHAR(255) NOT NULL,
       file_path VARCHAR(255) NOT NULL,
       summary TEXT,
       created_time DATETIME NOT NULL,
       FOREIGN KEY (knowledge_base_id) REFERENCES user_knowledge_bases(kb_id)
   );

   -- 用户知识库表
   CREATE TABLE user_knowledge_bases (
       kb_id VARCHAR(36) PRIMARY KEY,
       user_id VARCHAR(36) NOT NULL,
       title VARCHAR(255) NOT NULL,
       created_time DATETIME NOT NULL,
       FOREIGN KEY (user_id) REFERENCES users(user_id)
   );
   ```

   数据库表说明：
   - `users`: 存储用户信息
   - `conversations`: 存储对话信息
   - `messages`: 存储消息内容
   - `conversation_messages`: 对话和消息的关联表
   - `tool_calls`: 存储工具调用记录
   - `message_tool_calls`: 消息和工具调用的关联表
   - `user_conversations`: 用户和对话的关联表
   - `knowledge_base_files`: 存储知识库文件信息，与用户知识库表关联
   - `user_knowledge_bases`: 存储用户知识库信息，与用户表关联

## 运行项目

启动所有服务：
```bash
python src/main.py
```

## 项目结构

```
AI-Agent/
├── src/                    # 源代码目录
│   ├── GPTServer/         # GPT 服务相关代码
│   ├── MCPServer/         # 其他服务相关代码
│   ├── config/            # 配置文件
│   ├── database/          # 数据库相关代码
│   ├── interface/         # 接口定义
│   └── main.py           # 主程序入口
├── tests/                 # 测试文件
├── db/                    # 数据库文件
├── requirements.txt       # 项目依赖
└── README.md             # 项目说明文档
```

## 注意事项

- 请确保所有必要的 API 密钥都已正确配置
- 建议在生产环境中使用环境变量存储敏感信息
- 确保数据库服务正常运行