from openai import OpenAI

from ..interface.EnumModel import EnumModel
from ..interface.Messages import Messages

class GPTModel:
    client: OpenAI
    model:EnumModel


    def __init__(self,base_url,api_key,model):
        self.client = OpenAI(base_url=base_url,api_key=api_key)
        self.model = model

    def chat_stream(self, messages:Messages, tools=None, temperature=0):
        if tools is None:
            tools = []
        completion = self.client.chat.completions.create(
            model=self.model.value,
            messages=messages.get_messages(),
            tools=tools,
            # tool_choice="auto",
            temperature=temperature,
            stream=True
        )
        return completion
    
    def generate_summary(self, text: str) -> str:
        system_prompt = f"""
        你是一个专业的对话标题生成器，请根据用户输入的内容生成一个简洁明了的概述。
        请生成一个标题，要求：
        1. 简洁明了，不超过100个字
        2. 能够准确反映内容
        3. 使用中文
        """

        messages = Messages()
        messages.add_system_message(system_message=system_prompt)
        messages.add_user_message(text)

        completion = self.client.chat.completions.create(
            model=self.model.value,
            messages=messages.get_messages()
        )
        return completion.choices[0].message.content
    
    def embed_texts(self, texts,model=EnumModel.TEXT_EMBEDDING_3_SMALL) -> list:
        embeds = []
        for text in texts:
            response = self.client.embeddings.create(
                input=text,
                model=model.value
            )
            embeds.append(response.data[0].embedding)
        return embeds
            

