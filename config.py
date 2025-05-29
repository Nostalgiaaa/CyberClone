# --- 配置 ---
OLLAMA_MODEL_NAME = "qwen3:14b"  # 您在 Ollama 中部署的模型名
OLLAMA_BASE_URL = "http://localhost:11434"  # 您的 Ollama 服务地址
AVATAR_IMAGE_PATH = "./img/avatar.png"  # 【新增/修改】确保您的头像图片在此路径
MEMORY_K = 10  # 保留最近10轮对话
CHAT_MEMORY_DIR = "./memory/chat_memory"  # 向量数据库存储目录
HISTORY_PAGE_SIZE = 5  # 每页显示的历史记录数
TTS_BASE_URL = "http://localhost:9872/"  # TTS服务地址
TTS_REF_WAV_PATH = "./TTS/train/参考.wav"  # TTS参考音频路径
TTS_REF_TEXT = "模型切换，请上传并填写参考信息，请填写需要合成的目标文本和语种模式"  # TTS参考文本