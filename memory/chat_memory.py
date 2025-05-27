import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import uuid

class ChatMemory:
    def __init__(self, persist_directory: str = "./memory/chat_memory"):
        """初始化聊天记忆存储
        
        Args:
            persist_directory: 存储目录路径
        """
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="chat_history",
            metadata={"description": "Store chat history with vector embeddings"}
        )

    def add_interaction(self, 
                       user_input: str, 
                       assistant_response: str, 
                       metadata: Dict[Any, Any] = None) -> None:
        """添加一条新的对话记录
        
        Args:
            user_input: 用户输入
            assistant_response: AI助手回复
            metadata: 额外的元数据
        """
        if metadata is None:
            metadata = {}
        
        # 生成唯一ID和时间戳
        unique_id = str(uuid.uuid4())
        timestamp = int(datetime.now().timestamp() * 1000)  # 毫秒级时间戳
        
        # 构建完整的元数据
        full_metadata = {
            "timestamp": timestamp,
            "type": "chat_interaction",
            "user_input": user_input,  # 存储原始用户输入
            "assistant_response": assistant_response,  # 存储原始AI回复
            **metadata
        }
        
        # 构建用于向量搜索的文本
        search_text = f"{user_input}\n{assistant_response}"
        
        # 将对话添加到集合中
        self.collection.add(
            documents=[search_text],  # 用于向量搜索的组合文本
            metadatas=[full_metadata],
            ids=[unique_id]
        )
    
    def get_recent_interactions(self, 
                              page: int = 1,
                              page_size: int = 5,
                              include_total: bool = True) -> Tuple[List[Dict], int]:
        """获取对话记录，支持分页
        
        Args:
            page: 页码（从1开始）
            page_size: 每页记录数
            include_total: 是否返回总记录数
            
        Returns:
            Tuple[List[Dict], int]: (对话记录列表, 总记录数)
        """
        # 获取总记录数
        total_count = 0
        if include_total:
            all_count = self.collection.get()
            total_count = len(all_count["ids"]) if all_count["ids"] else 0
            
        if total_count == 0:
            return [], 0
            
        # 计算总页数和当前页
        total_pages = (total_count + page_size - 1) // page_size
        actual_page = total_pages - page + 1  # 从最后一页倒数
        
        if actual_page < 1:
            return [], total_count
            
        # 获取当前时间戳
        current_timestamp = int(datetime.now().timestamp() * 1000)
        
        # 使用时间戳范围查询，每次获取一页数据
        results = None
        for i in range(actual_page):
            if results is None:
                # 第一次查询，获取最新的记录
                results = self.collection.get(
                    where={"timestamp": {"$lte": current_timestamp}},
                    limit=page_size
                )
            else:
                # 获取下一页（更早的记录）
                if not results["metadatas"]:
                    break
                    
                # 获取当前页最早记录的时间戳
                min_timestamp = min(m["timestamp"] for m in results["metadatas"])
                
                # 查询更早的记录
                results = self.collection.get(
                    where={"timestamp": {"$lt": min_timestamp}},
                    limit=page_size
                )
        
        # 格式化结果
        interactions = []
        if results and results["ids"]:
            # 按时间戳倒序排序
            sorted_indices = list(range(len(results["ids"])))
            sorted_indices.sort(
                key=lambda i: results["metadatas"][i]["timestamp"],
                reverse=True  # 倒序排序，最新的在前
            )
            
            for idx in sorted_indices:
                print(results["metadatas"][idx])
                metadata = results["metadatas"][idx]
                # 将数值型时间戳转换回ISO格式用于显示
                display_timestamp = datetime.fromtimestamp(
                    metadata["timestamp"] / 1000
                ).isoformat()
                
                # 构建返回数据
                interaction_data = {
                    "id": results["ids"][idx],
                    "user_input": metadata["user_input"],
                    "assistant_response": metadata["assistant_response"],
                    "metadata": {
                        "timestamp": metadata["timestamp"],
                        "display_timestamp": display_timestamp,
                        **{k: v for k, v in metadata.items() 
                           if k not in ["timestamp", "type", "user_input", "assistant_response"]}
                    }
                }
                interactions.append(interaction_data)
        
        return interactions, total_count
    
    def format_interactions_for_display(self, interactions: List[Dict]) -> List[Dict[str, Any]]:
        """将对话记录格式化为 Chainlit 消息格式
        
        Args:
            interactions: 对话记录列表
            
        Returns:
            List[Dict[str, Any]]: Chainlit 消息列表
        """
        formatted_messages = []
        for interaction in interactions:
            timestamp = datetime.fromisoformat(interaction["metadata"]["display_timestamp"])
            formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            # 添加用户消息
            formatted_messages.append({
                "author": "用户",
                "content": interaction["user_input"],
                "metadata": {"timestamp": formatted_time}
            })
            
            # 添加AI回复
            formatted_messages.append({
                "author": "AI助手",
                "content": interaction["assistant_response"],
                "metadata": {"timestamp": formatted_time}
            })
        
        return formatted_messages
    
    def search_similar_interactions(self, 
                                  query: str, 
                                  n_results: int = 5) -> Dict:
        """搜索相似的历史对话"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        
        return results
    
    def clear_old_interactions(self, days_to_keep: int = 30) -> int:
        """清理旧的对话记录"""
        cutoff_timestamp = int(
            (datetime.now() - timedelta(days=days_to_keep)).timestamp() * 1000
        )
        
        # 获取需要删除的记录
        results = self.collection.get(
            where={"timestamp": {"$lt": cutoff_timestamp}}
        )
        
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            return len(results["ids"])
        
        return 0
        
    def clear_all(self) -> int:
        """清空所有对话记录
        
        Returns:
            int: 删除的记录数量
        """
        # 获取所有记录
        results = self.collection.get()
        
        if results["ids"]:
            count = len(results["ids"])
            self.collection.delete(ids=results["ids"])
            return count
            
        return 0 