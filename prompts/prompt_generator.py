import json
from typing import Dict, Any

def load_user_config(config_path: str) -> Dict[str, Any]:
    """加载用户配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_personality_description(config: Dict[str, Any]) -> str:
    """根据用户配置生成性格描述部分"""
    basic_info = config['user_profile']['basic_info']
    personality = config['user_profile']['personality']
    
    description = [
        f"你称呼自己为{basic_info['name']['value']}，",
        f"一位{basic_info['occupation']['value']}。"
    ]
    
    if basic_info.get('mbti', {}).get('value'):
        description.append(f"你的MBTI性格类型是{basic_info['mbti']['value']}。")
    
    if personality['core_traits']['value']:
        description.append(f"你的性格特点是：{personality['core_traits']['value']}。")
    
    if personality['values']['value']:
        description.append(f"你重视的价值观包括：{personality['values']['value']}。")
    
    if personality['interests']['value']:
        description.append(f"你的兴趣爱好是：{personality['interests']['value']}。")
    
    return ' '.join(description)

def generate_communication_style(config: Dict[str, Any]) -> str:
    """生成沟通风格描述"""
    comm_style = config['communication_style']
    
    style_desc = [
        f"你的说话语气是{comm_style['language_tone']['value']}。"
    ]
    
    speaking_habits = comm_style['speaking_habits']
    if speaking_habits.get('sentence_endings', {}).get('value'):
        style_desc.append(f"你偶尔使用的语气词包括：{speaking_habits['sentence_endings']['value']}。")
    
    response_style = comm_style['response_style']
    style_desc.append(
        f"你的回答倾向于{response_style['verbosity']['value']}，"
        f"语言风格{response_style['formality']['value']}。"         
    )
    
    return ' '.join(style_desc)

def generate_response_guidelines(config: Dict[str, Any]) -> str:
    """生成回应指南"""
    guidelines = config['response_generation_guidelines']
    
    return (
        f"在回答时，你应该保持{guidelines['length_preference']['value']}的长度，"
        f"{guidelines['directness']['value']}地表达，"
        f"以{guidelines['information_density']['value']}的方式传递信息，"
        f"并采用{guidelines['interaction_style']['value']}的互动方式。"
    )

def generate_examples_and_restrictions(config: Dict[str, Any]) -> str:
    """生成示例回答和限制说明"""
    examples = config['example_responses']['examples']
    uncharacteristic = config['uncharacteristic_statements']['examples']
    
    example_desc = ["以下是一些你的典型回答方式："]
    for ex in examples:
        if ex.get('your_response'):  # 只添加有回应的示例
            example_desc.append(
                f"当被问到「{ex['user_message']}」时，"
                f"你会回答：「{ex['your_response']}」"
            )
    
    restrict_desc = ["\n以下是你绝对不会使用的表达方式："]
    for un in uncharacteristic:
        restrict_desc.append(
            f"当遇到「{un['user_message']}」时，"
            f"你绝不会说：「{un['your_response']}」"
        )
    
    return '\n'.join(example_desc + restrict_desc)

def generate_prompt(config_path: str) -> str:
    """生成完整的提示词"""
    config = load_user_config(config_path)
    
    sections = [
        "# 角色设定",
        generate_personality_description(config),
        "\n# 沟通风格",
        generate_communication_style(config),
        "\n# 回应指南",
        generate_response_guidelines(config),
        "\n# 示例与限制",
        generate_examples_and_restrictions(config),
        "\n# 最终指令",
        "请严格按照以上设定进行回答。保持一致的性格特征和语言风格，"
        "避免使用已标注的不恰当表达方式。在回答问题时，要适当的体现出你的专业背景和个性特征，，同时句尾词使用可以自然地使用，但不要每句都用。"
        "尽量简洁，但确保表达完整和自然，平均长度在60-100字左右，避免不必要的冗长，不要重复的回答问题。"
        
    ]
    
    return '\n'.join(sections)

if __name__ == '__main__':
    # 测试代码
    prompt = generate_prompt('prompts/user_config.json')
    print(prompt) 