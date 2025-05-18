from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

@dataclass
class User:
    user_id: str
    username: str
    password: str
    create_time: datetime
    settings: Optional[str]

@dataclass
class Conversation:
    conversation_id: str
    title: Optional[str]
    create_time: datetime
    update_time: datetime
    status: str  # 'active' or 'deleted'

@dataclass
class Message:
    message_id: str
    role: str  # 'system', 'user', 'assistant', 'tool'
    content: Optional[str]
    created_time: datetime
    tool_call_id: Optional[str]
    tool_calls: Optional[str]

@dataclass
class ConversationMessage:
    conversation_id: str
    message_id: str
    create_time: datetime

@dataclass
class UserConversation:
    user_id: str
    conversation_id: str
    create_time: datetime

@dataclass
class KnowledgeBaseFile:
    file_id: str
    knowledge_base_id: str
    file_name: str
    file_path: str
    summary: str
    created_time: datetime

@dataclass
class UserKnowledgeBase:
    kb_id: str
    user_id: str
    title: str
    created_time: datetime

@dataclass
class ToolCall:
    call_id: str
    tool_name: str
    tool_parameters: Optional[Dict[str, Any]]
    status: str  # 'success' or 'failed'
    result: Optional[Dict[str, Any]]
    create_time: datetime

@dataclass
class MessageToolCall:
    message_id: str
    tool_call_id: str
    create_time: datetime