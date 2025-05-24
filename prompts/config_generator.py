import json
import logging
import re
from typing import Dict, Any, List, Tuple
from langchain_community.llms import Ollama

logger = logging.getLogger(__name__)

class ConfigGenerator:
    """配置生成器类，负责生成和保存用户配置"""
    
    def __init__(self, model_name: str = "qwen3:14b", base_url: str = "http://localhost:11434"):
        self.template_path = "prompts/template.json"
        self.output_path = "prompts/user_config.json"
        self.llm = Ollama(
            model=model_name,
            base_url=base_url,
        )
        
    @staticmethod
    def _clean_llm_response(response: str) -> str:
        """清理LLM返回的内容，移除思考过程等标记
        
        Args:
            response: LLM返回的原始响应
            
        Returns:
            清理后的JSON字符串
        """
        # 移除<think>标签及其内容
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        
        # 尝试找到JSON内容
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json_match.group()
            
        # 如果没有找到JSON，返回原始内容
        return response
        
    def load_template(self) -> Dict[str, Any]:
        """加载配置模板"""
        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = json.load(f)
                logger.info("成功加载模板文件: %s", self.template_path)
                return template
        except FileNotFoundError:
            logger.error("模板文件不存在: %s", self.template_path)
            raise
        except json.JSONDecodeError as e:
            logger.error("模板文件格式错误: %s - %s", self.template_path, str(e))
            raise
            
    def _extract_value_fields(self, template: Dict[str, Any], path: str = "") -> List[Tuple[str, str, Any]]:
        """提取模板中的value字段及其描述
        返回格式: [(json_path, description, current_value), ...]
        """
        result = []
        for key, value in template.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                if "value" in value and "description" in value:
                    # 找到一个value/description对
                    result.append((current_path, value["description"]))
                else:
                    # 继续递归搜索
                    result.extend(self._extract_value_fields(value, current_path))
        return result

    def _update_config_by_path(self, config: Dict[str, Any], path: str, value: Any) -> None:
        """根据JSON路径更新配置值"""
        parts = path.split('.')
        current = config
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        if isinstance(current[parts[-1]], dict) and "value" in current[parts[-1]]:
            # 如果是value/description结构，只更新value字段
            current[parts[-1]]["value"] = value
        else:
            # 否则直接更新整个值
            current[parts[-1]] = {"value": value}

    def _create_prompt_for_values(self, value_fields: List[Tuple[str, str, Any]], chat_content: str) -> str:
        """创建用于获取值的提示"""
        fields_desc = "\n".join([
            f"- {path}:\n  描述: {description}\n"
            for path, description in value_fields
        ])
        
        prompt = f"""
        你是一个专业的用户画像分析师。下面是聊天记录内容：
        {chat_content}
        
        请根据以下聊天记录按照 {fields_desc} 的输入，逐条分析给出结果。请按照以下格式返回每个字段的值（保持JSON格式）：
        {{
            "字段路径": "新的值",
            ...
        }}
        
        要求：
        1. 必须是合法的JSON格式
        2. 只返回字段的值，不要包含描述信息
        3. 分析要准确且有依据
        4. 保持字段路径完全一致
        """
        
        logger.info("生成的提示词长度: %d", len(prompt))
        return prompt

    def generate_config(self, chat_content: str) -> Dict[str, Any]:
        """使用本地Qwen3模型生成配置"""
        # 加载模板
        template = self.load_template()
        
        # 提取值字段
        value_fields = self._extract_value_fields(template)
        logger.info("提取了 %d 个需要填充的字段", len(value_fields))
        
        # 生成提示词
        prompt = self._create_prompt_for_values(value_fields, chat_content)
        
        try:
            logger.info("开始生成配置...")
            response = self.llm.invoke(prompt)
            logger.debug("模型原始响应: %s", response)
            
            # 清理响应内容
            cleaned_response = self._clean_llm_response(response)
            logger.debug("清理后的响应: %s", cleaned_response)
            
            # 尝试解析JSON
            values = json.loads(cleaned_response)
            print(values)
            logger.info("成功解析模型返回的JSON，字段数: %d", len(values))
            
            # 创建新的配置（基于原始模板）
            config = template.copy()
            for path, value in values.items():
                self._update_config_by_path(config, path, value)
            
            # 验证配置结构
            self._validate_config(config, template)
            return config
            
        except json.JSONDecodeError as e:
            logger.error("模型返回的内容不是有效的JSON格式: %s", str(e))
            logger.error("模型返回内容: %s", response)
            raise ValueError("模型返回的内容不是有效的JSON格式，请检查模型输出")
    
    def _validate_config(self, config: Dict[str, Any], template: Dict[str, Any]) -> None:
        """验证生成的配置是否符合模板结构"""
        def check_structure(conf: Dict[str, Any], temp: Dict[str, Any], path: str = "") -> None:
            # 检查配置中是否有模板中不存在的字段
            for key in conf:
                if key not in temp:
                    logger.warning("配置包含多余字段: %s%s", path, key)
            
            # 检查模板中的字段是否都存在，并且类型匹配
            for key in temp:
                if key not in conf:
                    logger.warning("配置缺少字段: %s%s", path, key)
                elif isinstance(temp[key], dict):
                    if not isinstance(conf[key], dict):
                        logger.warning("字段类型不匹配: %s%s 应为dict类型", path, key)
                    else:
                        # 如果是value/description结构，检查value字段
                        if "value" in temp[key] and "description" in temp[key]:
                            if "value" not in conf[key]:
                                logger.warning("配置缺少value字段: %s%s", path, key)
                        else:
                            check_structure(conf[key], temp[key], f"{path}{key}.")
        
        check_structure(config, template)
        logger.info("配置结构验证完成")
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """保存生成的配置文件"""
        try:
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
                logger.info("配置文件已保存到: %s", self.output_path)
        except IOError as e:
            logger.error("保存配置文件失败: %s - %s", self.output_path, str(e))
            raise 