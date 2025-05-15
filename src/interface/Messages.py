class Messages:
    messages: []

    def __init__(self):
        self.messages = []

    def get_messages(self):
        return self.messages

    def add_tool_message(self, tool_call_id, function_result):
        self.messages.append(self._transform_tool_message(tool_call_id, function_result))

    def add_system_message(self, system_message: str):
        self.messages.append(self._transform_system_message(prompt=system_message))

    def add_user_message(self, user_message: str):
        self.messages.append(self._transform_user_message(question=user_message))

    def add_assistant_message(self, assistant_message: str):
        self.messages.append(self._transform_assistant_message(answer=assistant_message))

    def add_assistant_tool_call_message(self, tool_calls:list):
        self.messages.append(self._transform_assistant_tool_call_message(tool_calls=tool_calls))

    def delete_system_message(self):
        self.messages = [message for message in self.messages if message['role'] != 'system']   

    def filter_valid_conversation_messages(self):
        """只保留用户消息和内容不为空的助手消息"""
        self.messages = [
            message for message in self.messages 
            if (message['role'] == 'user') or 
               (message['role'] == 'assistant' and message.get('content'))
        ]

    def _transform_tool_message(self, tool_call_id, function_result):
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": function_result,
        }

    def _transform_system_message(self, prompt):
        return {
            'role': 'system',
            'content': prompt
        }

    def _transform_user_message(self, question):
        return {
            'role': 'user',
            'content': question
        }

    def _transform_assistant_message(self, answer):
        return {
            'role': 'assistant',
            'content': answer
        }

    def _transform_assistant_tool_call_message(self, tool_calls):
        return {
            "role": "assistant",
            "tool_calls": tool_calls,
            "content": None
        }