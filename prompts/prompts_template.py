# 修改提示模板，加入个性化设定
prompt_template_str = """{personality_config}

历史对话：
{history}

用户问题：{input}

请根据以上角色设定和对话历史来回答问题。回答时要自然流畅，不要提及或显式引用角色设定。
回答："""