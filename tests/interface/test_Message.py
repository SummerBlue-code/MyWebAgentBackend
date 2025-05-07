import unittest

from src.interface import Messages

class TestMessageClass(unittest.TestCase):

    messages:Messages

    def setUp(self):
        self.messages = Messages()

    def tearDown(self):
        self.messages = None

    def test_add_tool_message(self):
        self.messages.add_tool_message(tool_call_id=5423,function_name="web_search",function_result="周杰伦是一个...")
        success_messages = [
            {
                'tool_call_id': 5423,
                'role': 'tool',
                'name': 'web_search',
                'content': '周杰伦是一个...'
            }
        ]
        self.assertEqual(
            self.messages.get_messages(),
            success_messages,
            "Message类的tool消息测试失败"
        )

    def test_add_system_message(self):
        self.messages.add_system_message("你是一个AI助手")
        success_messages = [
            {
                'role': 'system',
                'content': '你是一个AI助手'
             }
        ]
        self.assertEqual(
            self.messages.get_messages(),
            success_messages,
            "Message类的system消息测试失败"
        )

    def test_add_user_message(self):
        self.messages.add_user_message("请问周杰伦是谁？")
        success_messages = [
            {
                'role': 'user',
                'content': '请问周杰伦是谁？'
            }
        ]
        self.assertEqual(
            self.messages.get_messages(),
            success_messages,
            "Message类的user消息测试失败"
        )


if __name__ == '__main__':
    unittest.main()
