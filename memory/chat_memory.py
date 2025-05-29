import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import uuid
import time # 确保 time 模块被导入以使用 time.sleep

class ChatMemory:
    def __init__(self, persist_directory: str = "./memory/chat_memory"):
        """初始化聊天记忆存储
        
        Args:
            persist_directory: 存储目录路径
        """
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="chat_history",
            metadata={"description": "存储聊天历史及对应的向量嵌入"}
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
    
    def get_all_interactions_sorted(self) -> List[Dict]:
        """获取所有对话记录，并按时间戳倒序排列（最新的在前）。
                    
        Returns:
            List[Dict]: 所有对话记录的列表，已格式化并排序。
        """
        # import pdb;pdb.set_trace()
        all_results = self.collection.get(include=["metadatas"]) # IDs 默认返回

        interactions = []
        if all_results and all_results["ids"]:
            temp_list_for_sorting = []
            meta_map = {id_val: meta for id_val, meta in zip(all_results.get("ids", []), all_results.get("metadatas", []))}

            for id_val in all_results["ids"]:
                metadata = meta_map.get(id_val)
                if metadata and \
                   "timestamp" in metadata and \
                   metadata.get("user_input") is not None and \
                   metadata.get("assistant_response") is not None:
                    temp_list_for_sorting.append({
                        "id": id_val,
                        "user_input": metadata["user_input"],
                        "assistant_response": metadata["assistant_response"],
                        "timestamp": metadata["timestamp"],
                        "original_metadata": metadata
                    })
            
            # 按时间戳降序（最新的在前）
            temp_list_for_sorting.sort(key=lambda x: x["timestamp"], reverse=True)
            
            for item in temp_list_for_sorting:
                metadata = item["original_metadata"]
                display_timestamp = datetime.fromtimestamp(item["timestamp"] / 1000).isoformat()
                
                interaction_data = {
                    "id": item["id"],
                    "user_input": item["user_input"],
                    "assistant_response": item["assistant_response"],
                    "metadata": {
                        "timestamp": item["timestamp"],
                        "display_timestamp": display_timestamp,
                        **{k: v for k, v in metadata.items() 
                           if k not in ["timestamp", "type", "user_input", "assistant_response"]}
                    }
                }
                interactions.append(interaction_data)
        
        return interactions
    
    def format_interactions_for_display(self, interactions: List[Dict]) -> List[Dict[str, Any]]:
        """将对话记录格式化为 Chainlit 消息格式
        
        Args:
            interactions: 对话记录列表 (期望这里的interactions已经是按所需顺序排列好的)
            
        Returns:
            List[Dict[str, Any]]: Chainlit 消息列表
        """
        formatted_messages = []
        for interaction in interactions: # 假设传入的 interactions 已经是期望的显示顺序
            if "metadata" in interaction and "display_timestamp" in interaction["metadata"]:
                try:
                    timestamp = datetime.fromisoformat(interaction["metadata"]["display_timestamp"])
                    formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_time = "无效时间"
            else:
                formatted_time = "未知时间"
            
            user_input = interaction.get("user_input", "[用户输入缺失]")
            assistant_response = interaction.get("assistant_response", "[AI回复缺失]")

            formatted_messages.append({
                "author": "用户",
                "content": user_input,
                "metadata": {"timestamp": formatted_time}
            })
            
            formatted_messages.append({
                "author": "AI助手",
                "content": assistant_response,
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
            include=["metadatas", "documents"]
        )
        
        return results
    
    def clear_old_interactions(self, days_to_keep: int = 30) -> int:
        """清理旧的对话记录"""
        cutoff_timestamp = int(
            (datetime.now() - timedelta(days=days_to_keep)).timestamp() * 1000
        )
        
        results = self.collection.get(
            where={"timestamp": {"$lt": cutoff_timestamp}}
        )
        
        if results and results["ids"]:
            self.collection.delete(ids=results["ids"])
            return len(results["ids"])
        
        return 0
        
    def clear_all(self) -> int:
        """清空所有对话记录
        
        Returns:
            int: 删除的记录数量
        """
        all_results = self.collection.get() 
        all_ids = all_results.get("ids", [])

        if all_ids:
            count = len(all_ids)
            self.collection.delete(ids=all_ids)
            return count
        return 0 
    
if __name__ == "__main__":
    chat_memory = ChatMemory()
    
    print("清空所有记录...")
    chat_memory.clear_all()
    print("添加10条测试数据...")
    for i in range(10):
        chat_memory.add_interaction(f"用户说{i}", f"AI回复{i}", metadata={"custom_field": f"value_{i}"})
        time.sleep(0.01) 
    print("测试数据添加完毕.")

    print("\n--- 测试获取所有排序后的交互记录 ---")
    all_sorted_interactions = chat_memory.get_all_interactions_sorted()
    print(f"获取到的总交互数: {len(all_sorted_interactions)}")
    # 打印时，因为获取的是时间倒序（最新的在前），所以直接打印就是最新的在前
    for item in all_sorted_interactions:
        print(f"  ID: {item['id']}, Time: {item['metadata']['display_timestamp']}, User: {item['user_input']}")

    # 如果要在 __main__ 中模拟 app.py 的显示顺序 (最老的在前)
    print("\n--- 模拟 app.py 显示顺序 (最老的在前) --- ")
    if all_sorted_interactions:
        # format_interactions_for_display 期望的输入顺序就是最终显示顺序
        # 所以如果想让老的在前，需要反转 get_all_interactions_sorted 的结果
        display_ordered_interactions = list(reversed(all_sorted_interactions))
        formatted_for_display = chat_memory.format_interactions_for_display(display_ordered_interactions)
        for msg in formatted_for_display:
            print(f"  Author: {msg['author']}, Content: {msg['content']}, Time: {msg['metadata']['timestamp']}")

