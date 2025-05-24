import re
from typing import List, Dict, Any

class DataCleaner:
    """数据清洗类，负责处理敏感信息"""
    
    def __init__(self):
        # 敏感信息正则表达式模式
        self.patterns = {
            '身份证': r'\d{17}[\dXx]|\d{15}',
            '手机号': r'1[3-9]\d{9}',
            '银行卡': r'\d{16,19}',
            '邮箱': r'\w+@\w+\.\w+',
            '地址': r'(?:省|市|区|县|路|街|号楼?)\d+号?',
            'IP地址': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
            '金额': r'(?:¥|\$)?\d+(?:\.\d{2})?(?:元|万元|块钱)?'
        }
        
    def contains_sensitive_info(self, text: str) -> bool:
        """检查文本是否包含敏感信息
        
        Args:
            text: 待检查的文本
            
        Returns:
            bool: 是否包含敏感信息
        """
        if not text:
            return False
            
        for pattern in self.patterns.values():
            if re.search(pattern, text):
                return True
        return False
        
    def filter_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤包含敏感信息的消息
        
        Args:
            messages: 消息列表
            
        Returns:
            List[Dict[str, Any]]: 过滤后的消息列表
        """
        return [
            msg for msg in messages 
            if not self.contains_sensitive_info(msg.get('content', ''))
        ] 