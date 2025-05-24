import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Set
from .data_cleaner import DataCleaner

logger = logging.getLogger(__name__)

class ChatProcessor:
    def __init__(self, chat_dir: str):
        self.chat_dir = chat_dir
        self.cleaner = DataCleaner()
        
    def read_chat_files(self) -> List[str]:
        """读取所有聊天记录文件"""
        chat_path = Path(self.chat_dir)
        
        if not chat_path.exists():
            raise FileNotFoundError(f"聊天记录目录不存在: {self.chat_dir}")
        
        # 存储被分析人的消息和相关的对话
        target_messages = []  # is_sender = 1 的消息
        related_messages: Dict[str, Set[str]] = {}  # 与目标用户有交互的其他用户的消息
        
        for file in chat_path.glob("**/*"):
            if file.is_file():
                logger.info(f"正在处理文件: {file}")
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        chat_data = json.load(f)
                        
                        # 按时间排序消息
                        messages = []
                        for msg in chat_data:
                            if msg.get('type_name') == '文本':  # 只处理文本类型的消息
                                content = msg.get('msg', '')
                                # 跳过包含敏感信息的消息
                                if self.cleaner.contains_sensitive_info(content):
                                    continue
                                messages.append({
                                    'content': content,
                                    'is_sender': msg.get('is_sender', 0),
                                    'timestamp': msg.get('timestamp', 0)
                                })
                except json.JSONDecodeError as e:
                    logger.error(f"解析JSON文件失败 {file}: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理文件 {file} 时出错: {str(e)}")
                    continue

        return messages
    
    def format_for_llm(self, chat_contents: List[str]) -> str:
        """将聊天记录格式化为适合大模型处理的格式"""
        formatted_content = (
            "以下是用户的聊天记录样本，请根据这些内容分析用户的性格特征、说话方式和专业领域。"
            "注意：带有[发送者]标记的是被分析对象的发言，其他是与其相关的对话内容，你只需要结合[对话]分析[发送者]的发言，一定不要分析其他对象：\n\n"
        )
        
        messages = []
        for content in chat_contents:
            if content['is_sender'] == 1:
                messages.append(f"[发送者]: {content['content']}")
            else:
                messages.append(f"[对话]: {content['content']}")
        
        formatted_content += "\n---\n".join(messages)
        return formatted_content 