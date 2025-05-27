import os
import chainlit as cl
from langchain_community.llms import Ollama 
from gradio_client import Client, file
import requests
from prompts.prompt_generator import generate_prompt
from memory import ShortTermMemory, ChatMemory
from config import *  # 导入所有配置项
from prompts.promote_template import prompt_template_str


@cl.on_chat_start
async def start_chat():
    # 初始化 Ollama LLM
    llm = Ollama(model=OLLAMA_MODEL_NAME, base_url=OLLAMA_BASE_URL)
    cl.user_session.set("llm", llm)
    
    # 初始化短期记忆和向量存储记忆
    memory = ShortTermMemory(k=MEMORY_K)
    chat_memory = ChatMemory(persist_directory=CHAT_MEMORY_DIR)
    cl.user_session.set("memory", memory)
    cl.user_session.set("chat_memory", chat_memory)
    
    # 获取最后一页的历史记录
    interactions, total_count = chat_memory.get_recent_interactions(
        page=1,
        page_size=HISTORY_PAGE_SIZE
    )
    
    if interactions:
        # 计算总页数
        total_pages = (total_count + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
        cl.user_session.set("total_pages", total_pages)
        cl.user_session.set("current_page", 1)
        
        # 创建操作按钮
        actions = []
        if total_pages > 1:
            actions.append(cl.Action(name="load_history", value="load", label="查看更早的对话"))
            
        # 发送历史消息
        messages = chat_memory.format_interactions_for_display(interactions)
        for msg in messages:
            m = cl.Message(
                content=msg["content"],
                author=msg["author"],
                metadata={"time": msg["metadata"]["timestamp"]},
            )
            await m.send()

    # 发送欢迎消息
    elements = []
    if os.path.exists(AVATAR_IMAGE_PATH):
        try:
            with open(AVATAR_IMAGE_PATH, "rb") as f:
                avatar_bytes = f.read()
            elements.append(
                cl.Image(
                    content=avatar_bytes,
                    name="avatar_pic_start",
                    display="inline",
                    size="medium",
                )
            )
        except Exception as e:
            print(f"错误：加载欢迎消息头像图片失败 - {e}")

    await cl.Message(
        content=f"你好！我是基于 **{OLLAMA_MODEL_NAME}** 模型的AI助手。请问有什么可以帮您的吗？",
        elements=elements,
        author="AI助手",
    ).send()

@cl.action_callback("load_history")
async def on_load_history(action):
    chat_memory = cl.user_session.get("chat_memory") # chat_memory 是 ChatMemory 类的实例
    current_page = cl.user_session.get("current_page", 1)
    total_pages = cl.user_session.get("total_pages", 1) 
    
    if current_page >= total_pages:
        return
    
    next_page = current_page + 1
    
    # 获取更早的历史记录
    interactions, _ = chat_memory.get_recent_interactions(
        page=next_page,
        page_size=HISTORY_PAGE_SIZE,
        include_total=False
    )
    
    if interactions:
        # 创建操作按钮
        actions = []
        if next_page < total_pages:
            actions.append(cl.Action(name="load_history", value="load", label="查看更早的对话"))
        
        # 更新当前页码
        cl.user_session.set("current_page", next_page)
        
        # 发送页码信息
        await cl.Message(
            content=f"历史对话记录（第{next_page}/{total_pages}页）：",
            actions=actions
        ).send()
        
        # 发送历史消息
        messages = chat_memory.format_interactions_for_display(interactions)
        for msg in messages:
            m = cl.Message(
                content=msg["content"],
                author=msg["author"],
                metadata={"time": msg["metadata"]["timestamp"]},
            )
            await m.send()

@cl.on_audio_start
async def on_audio_start():
    cl.user_session.set("silent_duration_ms", 0)
    cl.user_session.set("is_speaking", False)
    cl.user_session.set("audio_chunks", [])
    return True


@cl.on_message
async def main(message: cl.Message):
    llm = cl.user_session.get("llm")
    memory = cl.user_session.get("memory")
    chat_memory = cl.user_session.get("chat_memory")  # 获取向量存储记忆
    user_message = message.content

    if not user_message:
        await cl.Message(content="请输入您的问题。", author="系统").send()
        return

    # 准备AI回复的头像
    ai_reply_elements = []
    if os.path.exists(AVATAR_IMAGE_PATH):
        try:
            with open(AVATAR_IMAGE_PATH, "rb") as f:
                avatar_bytes_reply = f.read()
            ai_reply_elements.append(
                cl.Image(
                    content=avatar_bytes_reply,
                    name="avatar_reply",
                    display="inline",
                    size="small",
                )
            )
        except Exception as e:
            print(f"错误：加载AI回复头像图片失败 - {e}")

    # ---- 初始化 Chainlit UI 元素 ----
    # 1. 创建 "AI 思考过程" 的步骤 UI，初始内容为空
    async with cl.Step(name="AI 思考过程", show_input=False) as think_step:
        think_step.output = ""  # 先设置为空，或者 "正在思考..."

        # 【修改】将头像元素加入 final_reply_msg，并设置 author
        final_reply_msg = cl.Message(
            content="", 
            author="AI助手", 
            elements=ai_reply_elements
        )
        await final_reply_msg.send()

        # 2. 创建最终回复的空消息 UI，用于流式填充
        final_reply_msg = cl.Message(content="")
        await final_reply_msg.send()  # 必须先发送空壳

        # ---- 变量用于流式解析 ----
        accumulated_think_content = ""  # 用于累积 <think> 标签内的内容
        current_processing_buffer = ""  # 用于处理跨 token 的标签
        is_inside_think_block = False  # 当前是否正在解析 <think> 标签内的内容
        reply_content = ""  #  记录 LLM 最终回复的结果，转成 LLM 用

        try:
            # 获取短期记忆历史对话
            history = memory.get_formatted_history()
            
            print("load history complete")
            # 搜索长期历史对话
            similar_interactions = chat_memory.search_similar_interactions(user_message, n_results=3)
            if similar_interactions and similar_interactions.get('documents'):
                # 从元数据中获取完整的对话内容
                relevant_history_list = []
                relevant_history = "\n相关历史对话：\n"
                for metadata in similar_interactions['metadatas']:
                    if len(metadata) == 0:
                        continue
                    relevant_history_list.append(f"用户: {metadata['user_input']}\n AI助手: {metadata['assistant_response']}\n")
                if len(relevant_history_list) > 0:
                    history += "\n相关历史对话：\n" + "\n".join(relevant_history_list)
            # 构建提示
            prompt = prompt_template_str.format(
                personality_config=generate_prompt('./prompts/user_config.json'),
                history=history,
                input=user_message
            )
            
            # 添加用户消息到记忆
            memory.add_user_message(user_message)
            
            print(f"DEBUG: Sending prompt to LLM: '{prompt[:300]}...'")

            async for token in llm.astream(prompt):
                if not token:
                    continue

                current_processing_buffer += token
                # print(f"DEBUG: Buffer: '{current_processing_buffer}' | InThink: {is_inside_think_block}")

                while True:  # 循环处理 buffer 中的内容，直到无法进一步解析
                    processed_in_loop = False
                    if is_inside_think_block:
                        end_tag_index = current_processing_buffer.find("</think>")
                        if end_tag_index != -1:
                            # 找到了 </think> 标签
                            think_chunk = current_processing_buffer[:end_tag_index]
                            accumulated_think_content += think_chunk
                            think_step.output = (
                                accumulated_think_content  # 更新思考步骤的全部内容
                            )

                            current_processing_buffer = current_processing_buffer[
                                end_tag_index + len("</think>") :
                            ]
                            is_inside_think_block = False
                            processed_in_loop = True
                            # print(f"DEBUG: Exited think block. Remaining buffer: '{current_processing_buffer}'")
                        else:
                            # 还在 think 标签内，但没找到结束标签，当前 buffer 不足以构成完整结束
                            # 将当前 buffer 的大部分（除了可能的标签开头）累加到思考内容中
                            # 为了避免过早更新UI，我们将累积，直到找到结束标签
                            # 或者，如果希望思考过程也流式展示在step中，这里的逻辑需要更复杂
                            # 目前的逻辑是找到完整的 <think>...</think> 后再更新 step.output
                            break  # 等待更多 token 来形成完整的 </think>
                    else:  # 不在 think 标签内，当前内容是回复
                        start_tag_index = current_processing_buffer.find("<think>")
                        if start_tag_index != -1:
                            # 找到了 <think> 标签
                            reply_chunk = current_processing_buffer[:start_tag_index]
                            if reply_chunk:
                                await final_reply_msg.stream_token(reply_chunk)

                            is_inside_think_block = True
                            current_processing_buffer = current_processing_buffer[
                                start_tag_index + len("<think>") :
                            ]
                            processed_in_loop = True
                            # print(f"DEBUG: Entered think block. Remaining buffer: '{current_processing_buffer}'")
                        else:
                            # 当前 buffer 中没有 <think> 标签，全部是回复内容
                            # 为了避免流式输出不完整的标签，我们可以做一个简单检查
                            # 如果 buffer 中没有 '<'，则可以安全地流式输出整个 buffer
                            if "<" not in current_processing_buffer:
                                if current_processing_buffer:
                                    reply_content += current_processing_buffer
                                    await final_reply_msg.stream_token(
                                        current_processing_buffer
                                    )
                                    current_processing_buffer = ""
                                processed_in_loop = (
                                    True  # 即使为空，也标记为处理过以退出循环
                                )
                            # 如果有 '<'，可能是标签的开头，暂时不处理，等待更多 token
                            break  # 等待更多 token

                    if not processed_in_loop:  # 如果内层循环没有处理任何东西，跳出
                        break

            # 流结束后，处理 current_processing_buffer 中剩余的内容
            if current_processing_buffer:
                if not is_inside_think_block:  # 如果最后是在回复状态
                    # print(f"DEBUG: Streaming remaining buffer as reply: '{current_processing_buffer}'")
                    reply_content += current_processing_buffer
                    await final_reply_msg.stream_token(current_processing_buffer)
                else:  # 如果流结束时仍在 think 块内（标签不完整）
                    # print(f"DEBUG: Appending remaining buffer to think content: '{current_processing_buffer}'")
                    accumulated_think_content += current_processing_buffer
                    think_step.output = accumulated_think_content  # 更新最后的思考内容

            # 最终检查和设置默认值
            if not think_step.output or think_step.output == "正在生成思考计划...":
                think_step.output = "(模型未提供明确的思考过程标签内容)"
            print("DEBUG: Stream processing complete.")
            if len(reply_content) <= 2:
                return

            # 添加AI回复到记忆
            if reply_content:
                memory.add_ai_message(reply_content)
                # 同时保存到向量数据库
                chat_memory.add_interaction(
                    user_input=user_message,
                    assistant_response=reply_content,
                    metadata={"model": OLLAMA_MODEL_NAME}
                )

            audio_path = text_to_speech(reply_content)
            output_audio_el = cl.Audio(
                name="语音",
                path=audio_path,
                display="inline",
            )

            await cl.Message(content="", elements=[output_audio_el]).send()

        except Exception as e:
            error_msg = f"处理流时出错: {str(e)}"
            print(e)
            print(f"ERROR: Exception during stream processing: {error_msg}")
            if final_reply_msg and final_reply_msg.id:
                await final_reply_msg.update()
            else:
                await cl.Message(content=error_msg).send()
            if think_step and think_step.id:  # 更新step的错误信息
                think_step.output = error_msg


def text_to_speech(text: str) -> str:
    """将文本转换为语音

    Args:
        text: 要转换的文本

    Returns:
        str: 生成的音频文件路径
    """
    try:
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        client = Client(TTS_BASE_URL)
        
        # 确保参考音频文件存在
        if not os.path.exists(TTS_REF_WAV_PATH):
            raise FileNotFoundError(f"参考音频文件不存在: {TTS_REF_WAV_PATH}")
            
        print(f"DEBUG: 开始TTS转换，文本长度: {len(text)}")
        print(f"DEBUG: 参考音频文件: {TTS_REF_WAV_PATH}")
        
        result = client.predict(
            ref_wav_path=file(TTS_REF_WAV_PATH),
            prompt_text=TTS_REF_TEXT,
            prompt_language="中文",
            text=text,
            text_language="中文",
            how_to_cut="凑四句一切",
            top_k=15,
            top_p=1,
            temperature=1,
            ref_free=False,
            speed=1,
            if_freeze=False,
            inp_refs=None,
            sample_steps=8,
            if_sr=False,
            pause_second=0.3,
            api_name="/get_tts_wav"
        )
        
        print(f"DEBUG: TTS转换完成，结果: {result}")
        return result
        
    except Exception as e:
        print(f"ERROR: TTS转换失败 - {str(e)}")
        raise
