from openai import OpenAI

from ..interface.EnumModel import EnumModel
from ..interface.Messages import Messages

class GPTModel:
    client: OpenAI
    model:EnumModel


    def __init__(self,base_url,api_key,model):
        self.client = OpenAI(base_url=base_url,api_key=api_key)
        self.model = model

    def chat_stream(self, messages:Messages, tools:list,temperature=0):
        completion = self.client.chat.completions.create(
            model=self.model.value,
            messages=messages.get_messages(),
            tools=tools,
            # tool_choice="auto",
            temperature=temperature,
            stream=True
        )
        return completion

