from typing import List, Dict, Any
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseChatMessageHistory

class ShortTermMemory:
    def __init__(self, k: int = 5):
        """初始化短期记忆
        
        Args:
            k: 保留的对话轮数
        """
        self.memory = ConversationBufferWindowMemory(
            k=k,
            return_messages=True,
            memory_key="history",
            input_key="input"
        )
        
    def add_user_message(self, message: str) -> None:
        """添加用户消息
        
        Args:
            message: 用户消息内容
        """
        self.memory.chat_memory.add_user_message(message)
        
    def add_ai_message(self, message: str) -> None:
        """添加AI消息
        
        Args:
            message: AI消息内容
        """
        self.memory.chat_memory.add_ai_message(message)
        
    def get_messages(self) -> List[Dict[str, str]]:
        """获取所有消息历史
        
        Returns:
            List[Dict[str, str]]: 消息历史列表
        """
        messages = []
        for msg in self.memory.chat_memory.messages:
            messages.append({
                "role": "user" if msg.type == "human" else "assistant",
                "content": msg.content
            })
        return messages
    
    def get_formatted_history(self) -> str:
        """获取格式化的历史记录
        
        Returns:
            str: 格式化的历史记录
        """
        messages = self.get_messages()
        formatted = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "AI"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def clear(self) -> None:
        """清空记忆"""
        self.memory.chat_memory.clear()
        
    def load_memory(self, messages: List[Dict[str, str]]) -> None:
        """加载历史消息
        
        Args:
            messages: 消息列表，每个消息包含 role 和 content
        """
        self.clear()
        for msg in messages:
            if msg["role"] == "user":
                self.add_user_message(msg["content"])
            else:
                self.add_ai_message(msg["content"])
                
    def get_relevant_history(self, query: str, k: int = 3) -> List[Dict[str, str]]:
        """获取与查询相关的历史消息
        
        Args:
            query: 查询内容
            k: 返回的消息数量
            
        Returns:
            List[Dict[str, str]]: 相关消息列表
        """
        # 简单实现：返回最近的k条消息
        # 后续可以添加相关性计算
        messages = self.get_messages()
        return messages[-k:] if len(messages) > k else messages 