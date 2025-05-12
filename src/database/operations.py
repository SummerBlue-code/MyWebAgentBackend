from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import Database
from .models import User, Conversation, Message, ConversationMessage, ToolCall, MessageToolCall, UserConversation, KnowledgeBaseFile, UserKnowledgeBase
from ..interface.Messages import Messages
import json
import logging

logger = logging.getLogger(__name__)

class DatabaseOperations:
    def __init__(self, db: Database):
        self.db = db

    # User 相关操作
    def create_user(self, user: User) -> bool:
        query = """
        INSERT INTO users (user_id, username, password, create_time, settings)
        VALUES (%s, %s, %s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                user.user_id, user.username, user.password, user.create_time, user.settings
            ))
            return True
        except Exception:
            return False

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        query = "SELECT * FROM users WHERE user_id = %s"
        result = self.db.execute_query(query, (user_id,))
        if result:
            data = result[0]
            return User(**data)
        return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        query = "SELECT * FROM users WHERE username = %s"
        result = self.db.execute_query(query, (username,))
        if result:
            data = result[0]
            return User(**data)
        return None

    def get_user_by_phone(self, phone_number: str) -> Optional[User]:
        query = "SELECT * FROM users WHERE phone_number = %s"
        result = self.db.execute_query(query, (phone_number,))
        if result:
            data = result[0]
            return User(**data)
        return None

    def update_user_server(self, server: dict, user_id: str) -> bool:
        """更新用户服务器设置"""
        query = "UPDATE users SET settings = %s WHERE user_id = %s"
        try:
            # 将字典转换为JSON字符串
            server_json = json.dumps(server, ensure_ascii=False)
            return self.db.execute_update(query, (server_json, user_id)) > 0
        except Exception as e:
            logger.error(f"更新用户服务器设置失败: {str(e)}")
            return False

    def get_user_settings(self, user_id: str) -> Optional[dict]:
        """获取用户服务器设置"""
        query = "SELECT settings FROM users WHERE user_id = %s AND settings IS NOT NULL"
        result = self.db.execute_query(query, (user_id,))
        logger.info(f"获取到用户 {user_id} 的服务器设置: {result}")
        if result:
            return json.loads(result[0]['settings'])
        return None

    # Conversation 相关操作
    def create_conversation(self, conversation: Conversation, user_id: str) -> bool:
        """创建对话并自动关联用户"""
        try:
            self.db.begin_transaction()
            
            # 创建对话
            query = """
            INSERT INTO conversations (conversation_id, title, create_time, update_time, status)
            VALUES (%s, %s, %s, %s, %s)
            """
            self.db.execute_insert(query, (
                conversation.conversation_id, conversation.title,
                conversation.create_time, conversation.update_time,
                conversation.status
            ))
            
            # 创建用户对话关联
            user_conversation = UserConversation(
                user_id=user_id,
                conversation_id=conversation.conversation_id,
                create_time=datetime.now()
            )
            self.link_user_to_conversation(user_conversation)
            
            self.db.commit_transaction()
            return True
        except Exception:
            self.db.rollback_transaction()
            return False

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        query = "SELECT * FROM conversations WHERE conversation_id = %s"
        result = self.db.execute_query(query, (conversation_id,))
        if result:
            data = result[0]
            return Conversation(**data)
        return None

    def update_conversation_status(self, conversation_id: str, status: str) -> bool:
        query = "UPDATE conversations SET status = %s WHERE conversation_id = %s"
        return self.db.execute_update(query, (status, conversation_id)) > 0

    def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        query = "UPDATE conversations SET title = %s WHERE conversation_id = %s"
        return self.db.execute_update(query, (title, conversation_id)) > 0

    # Message 相关操作
    def create_message(self, message: Message, conversation_id: str, tool_calls: Optional[List[ToolCall]] = None) -> bool:
        """创建消息并自动关联对话和工具调用"""
        try:
            self.db.begin_transaction()
            
            # 创建消息
            query = """
            INSERT INTO messages (message_id, role, content, created_time,tool_calls, tool_call_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.db.execute_insert(query, (
                message.message_id, message.role,
                message.content, message.created_time,
                message.tool_calls, message.tool_call_id
            ))
            
            # 创建对话消息关联
            conversation_message = ConversationMessage(
                conversation_id=conversation_id,
                message_id=message.message_id,
                create_time=datetime.now()
            )
            self.add_message_to_conversation(conversation_message)
            
            # 如果是工具消息且有工具调用，创建工具调用关联
            if message.role == 'tool' and tool_calls:
                for tool_call in tool_calls:
                    # 创建工具调用记录
                    self.create_tool_call(tool_call)
                    # 创建消息工具调用关联
                    message_tool_call = MessageToolCall(
                        message_id=message.message_id,
                        tool_call_id=tool_call.call_id,
                        create_time=datetime.now()
                    )
                    self.link_message_to_tool_call(message_tool_call)
            
            self.db.commit_transaction()
            return True
        except Exception:
            self.db.rollback_transaction()
            return False

    def get_message(self, message_id: str) -> Optional[Message]:
        query = "SELECT * FROM messages WHERE message_id = %s"
        result = self.db.execute_query(query, (message_id,))
        if result:
            data = result[0]
            return Message(**data)
        return None

    # ConversationMessage 相关操作
    def add_message_to_conversation(self, conversation_message: ConversationMessage) -> bool:
        query = """
        INSERT INTO conversation_messages (conversation_id, message_id, create_time)
        VALUES (%s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                conversation_message.conversation_id,
                conversation_message.message_id,
                conversation_message.create_time
            ))
            return True
        except Exception:
            return False

    def _convert_to_messages_format(self, db_messages: List[Message]) -> Messages:
        """将数据库消息转换为Messages格式"""
        messages = Messages()
        for msg in db_messages:
            if msg.role == 'system':
                messages.add_system_message(msg.content)
            elif msg.role == 'user':
                messages.add_user_message(msg.content)
            elif msg.role == 'assistant':
                if msg.tool_calls:
                    # 如果有工具调用，使用工具调用格式
                    tool_calls_list = json.loads(msg.tool_calls)
                    messages.add_assistant_tool_call_message(tool_calls_list)
                else:
                    # 如果没有工具调用，使用普通消息格式
                    messages.add_assistant_message(msg.content)
            elif msg.role == 'tool':
                # 确保tool_call_id不为空
                if msg.tool_call_id:
                    messages.add_tool_message(msg.tool_call_id, msg.content)
                else:
                    logger.warning(f"工具消息缺少tool_call_id: {msg}")
        return messages

    def get_conversation_messages(self, conversation_id: str) -> Messages:
        query = """
        SELECT m.* FROM messages m
        JOIN conversation_messages cm ON m.message_id = cm.message_id
        WHERE cm.conversation_id = %s
        ORDER BY cm.create_time
        """
        results = self.db.execute_query(query, (conversation_id,))
        db_messages = [Message(**data) for data in results]
        return self._convert_to_messages_format(db_messages)

    def get_message_list(self, conversation_id: str) -> Messages:
        query = """
        SELECT m.* FROM messages m
        JOIN conversation_messages cm ON m.message_id = cm.message_id
        WHERE cm.conversation_id = %s
        ORDER BY cm.create_time
        """
        results = self.db.execute_query(query, (conversation_id,))
        db_messages = [Message(**data) for data in results]

        return self._convert_to_messages_format(db_messages)

    # ToolCall 相关操作
    def create_tool_call(self, tool_call: ToolCall) -> bool:
        query = """
        INSERT INTO tool_calls (call_id, tool_name, tool_parameters, status, result, create_time)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                tool_call.call_id, tool_call.tool_name,
                json.dumps(tool_call.tool_parameters) if tool_call.tool_parameters else None,
                tool_call.status,
                json.dumps(tool_call.result) if tool_call.result else None,
                tool_call.create_time
            ))
            return True
        except Exception:
            return False

    def update_tool_call_status(self, call_id: str, status: str, result: Optional[Dict] = None) -> bool:
        query = """
        UPDATE tool_calls 
        SET status = %s, result = %s
        WHERE call_id = %s
        """
        return self.db.execute_update(query, (
            status,
            json.dumps(result) if result else None,
            call_id
        )) > 0

    # MessageToolCall 相关操作
    def link_message_to_tool_call(self, message_tool_call: MessageToolCall) -> bool:
        query = """
        INSERT INTO message_tool_calls (message_id, tool_call_id, create_time)
        VALUES (%s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                message_tool_call.message_id,
                message_tool_call.tool_call_id,
                message_tool_call.create_time
            ))
            return True
        except Exception:
            return False

    def get_message_tool_calls(self, message_id: str) -> List[ToolCall]:
        query = """
        SELECT tc.* FROM tool_calls tc
        JOIN message_tool_calls mtc ON tc.call_id = mtc.tool_call_id
        WHERE mtc.message_id = %s
        """
        results = self.db.execute_query(query, (message_id,))
        return [ToolCall(**data) for data in results]

    # UserConversation 相关操作
    def link_user_to_conversation(self, user_conversation: UserConversation) -> bool:
        query = """
        INSERT INTO user_conversations (user_id, conversation_id, create_time)
        VALUES (%s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                user_conversation.user_id,
                user_conversation.conversation_id,
                user_conversation.create_time
            ))
            return True
        except Exception:
            return False

    def get_user_conversations(self, user_id: str) -> List[Conversation]:
        query = """
        SELECT c.* FROM conversations c
        JOIN user_conversations uc ON c.conversation_id = uc.conversation_id
        WHERE uc.user_id = %s AND c.status = 'active'
        ORDER BY c.update_time DESC
        """
        results = self.db.execute_query(query, (user_id,))
        return [Conversation(**data) for data in results]

    # KnowledgeBaseFile 相关操作
    def create_knowledge_base_file(self, file: KnowledgeBaseFile) -> bool:
        query = """
        INSERT INTO knowledge_base_file (file_id, knowledge_base_id, file_name, file_path, summary, created_time)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                file.file_id, file.knowledge_base_id, file.file_name,
                file.file_path, file.summary, file.created_time
            ))
            return True
        except Exception as e:
            logger.error(f"创建知识库文件失败: {str(e)}")
            return False

    def get_knowledge_base_files(self, knowledge_base_id: str) -> List[KnowledgeBaseFile]:
        query = "SELECT * FROM knowledge_base_file WHERE knowledge_base_id = %s ORDER BY created_time DESC"
        results = self.db.execute_query(query, (knowledge_base_id,))
        return [KnowledgeBaseFile(**data) for data in results]

    def get_knowledge_base_file(self, file_id: str) -> Optional[KnowledgeBaseFile]:
        query = "SELECT * FROM knowledge_base_file WHERE file_id = %s"
        result = self.db.execute_query(query, (file_id,))
        if result:
            return KnowledgeBaseFile(**result[0])
        return None

    def delete_knowledge_base_file(self, file_id: str) -> bool:
        query = "DELETE FROM knowledge_base_file WHERE file_id = %s"
        return self.db.execute_delete(query, (file_id,)) > 0

    # UserKnowledgeBase 相关操作
    def create_user_knowledge_base(self, kb: UserKnowledgeBase) -> bool:
        query = """
        INSERT INTO user_knowledge_base (kb_id, user_id, title, created_time)
        VALUES (%s, %s, %s, %s)
        """
        try:
            self.db.execute_insert(query, (
                kb.kb_id, kb.user_id, kb.title, kb.created_time
            ))
            return True
        except Exception as e:
            logger.error(f"创建用户知识库失败: {str(e)}")
            return False

    def get_user_knowledge_bases(self, user_id: str) -> List[UserKnowledgeBase]:
        query = "SELECT * FROM user_knowledge_base WHERE user_id = %s ORDER BY created_time DESC"
        results = self.db.execute_query(query, (user_id,))
        return [UserKnowledgeBase(**data) for data in results]

    def get_knowledge_base(self, kb_id: str) -> Optional[UserKnowledgeBase]:
        query = "SELECT * FROM user_knowledge_base WHERE kb_id = %s"
        result = self.db.execute_query(query, (kb_id,))
        if result:
            return UserKnowledgeBase(**result[0])
        return None

    def update_knowledge_base_title(self, kb_id: str, title: str) -> bool:
        query = "UPDATE user_knowledge_base SET title = %s WHERE kb_id = %s"
        return self.db.execute_update(query, (title, kb_id)) > 0

    def delete_knowledge_base(self, kb_id: str) -> bool:
        query = "DELETE FROM user_knowledge_base WHERE kb_id = %s"
        return self.db.execute_delete(query, (kb_id,)) > 0