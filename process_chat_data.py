import os
import logging
from prompts import ChatProcessor, ConfigGenerator

# 禁用所有代理
os.environ['NO_PROXY'] = '*'

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ollama配置
OLLAMA_MODEL_NAME = "qwen3:14b"
OLLAMA_BASE_URL = "http://localhost:11434"

def main():
    try:
        logger.info("开始处理...")
        
        # 初始化处理器
        chat_processor = ChatProcessor("train_data/wechat")
        config_generator = ConfigGenerator(
            model_name=OLLAMA_MODEL_NAME,
            base_url=OLLAMA_BASE_URL
        )
        
        # 读取并清洗聊天记录
        logger.info("正在读取和清洗聊天记录...")
        chat_contents = chat_processor.read_chat_files()
        
        if not chat_contents:
            logger.error("没有找到任何聊天记录")
            raise ValueError("没有找到任何聊天记录")
        
        # 格式化聊天记录
        logger.info("正在格式化聊天内容...")
        formatted_content = chat_processor.format_for_llm(chat_contents)
        
        # 生成配置
        logger.info("正在生成配置文件...")
        config = config_generator.generate_config(formatted_content)
        
        # 保存配置
        logger.info("正在保存配置文件...")
        config_generator.save_config(config)
        
        logger.info(f"处理完成！配置文件已保存到：{config_generator.output_path}")
        
    except Exception as e:
        logger.error(f"发生错误：{str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 