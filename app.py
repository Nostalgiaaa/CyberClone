import os
import chainlit as cl
from langchain_community.llms import Ollama 
from gradio_client import Client, file
import requests
from prompts.prompt_generator import generate_prompt
from memory import ShortTermMemory

# --- 配置 ---
OLLAMA_MODEL_NAME = "qwen3:14b"  # 您在 Ollama 中部署的模型名
OLLAMA_BASE_URL = "http://localhost:11434"  # 您的 Ollama 服务地址
AVATAR_IMAGE_PATH = "./img/avatar.png"  # 【新增/修改】确保您的头像图片在此路径
WHISPER_MODEL_SIZE = "base"  # 新增：Whisper模型大小
MEMORY_K = 10  # 保留最近5轮对话

# 加载个性化提示词
try:
    personality_prompt = generate_prompt('./prompts/user_config.json')
except Exception as e:
    print(f"警告：加载个性化提示词失败 - {e}")
    personality_prompt = ""

# Define a threshold for detecting silence and a timeout for ending a turn
SILENCE_THRESHOLD = (
    3500  # Adjust based on your audio level (e.g., lower for quieter audio)
)
SILENCE_TIMEOUT = 1300.0  # Seconds of silence to consider the turn finished

# --- 初始化 LangChain 组件 ---
llm = Ollama(
    model=OLLAMA_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
)

# 修改提示模板，加入个性化设定
prompt_template_str = """{personality_config}

历史对话：
{history}

用户问题：{input}

请根据以上角色设定和对话历史来回答问题。回答时要自然流畅，不要提及或显式引用角色设定。
回答："""


@cl.on_chat_start
async def start_chat():
    # 初始化 Ollama LLM
    llm = Ollama(model=OLLAMA_MODEL_NAME, base_url=OLLAMA_BASE_URL)
    cl.user_session.set("llm", llm)
    
    # 初始化短期记忆
    memory = ShortTermMemory(k=MEMORY_K)
    cl.user_session.set("memory", memory)

    # 发送欢迎消息和AI头像图片
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
            print(f"DEBUG: 头像图片 '{AVATAR_IMAGE_PATH}' 已准备好在欢迎消息中显示。")
        except Exception as e:
            print(f"错误：加载欢迎消息头像图片失败 - {e}")
    else:
        print(f"警告：未找到头像图片路径 '{AVATAR_IMAGE_PATH}'。欢迎消息将不带头像。")

    # 【修改】将头像元素加入欢迎消息，并设置author
    await cl.Message(
        content=f"你好！我是基于 **{OLLAMA_MODEL_NAME}** 模型的AI助手。请问有什么可以帮您的吗？",
        elements=elements,  # 添加图片元素
        author="AI助手",  # 设置作者名，会显示在头像旁边
    ).send()


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
    #    这个 step 的 output 会在解析到完整的 <think>...</think> 内容后更新
    async with cl.Step(name="AI 思考过程", show_input=False) as think_step:
        think_step.output = ""  # 先设置为空，或者 "正在思考..."

        # 【修改】将头像元素加入 final_reply_msg，并设置 author
        final_reply_msg = cl.Message(
            content="", author="AI助手", elements=ai_reply_elements
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
            # 获取历史对话
            history = memory.get_formatted_history()
            
            # 构建提示
            prompt = prompt_template_str.format(
                personality_config=personality_prompt,
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
        client = Client("http://localhost:9872/")
        
        # 确保参考音频文件存在
        ref_wav_path = "./TTS/train/参考.wav"
        if not os.path.exists(ref_wav_path):
            raise FileNotFoundError(f"参考音频文件不存在: {ref_wav_path}")
            
        print(f"DEBUG: 开始TTS转换，文本长度: {len(text)}")
        print(f"DEBUG: 参考音频文件: {ref_wav_path}")
        
        result = client.predict(
            ref_wav_path=file(ref_wav_path),
            prompt_text="模型切换，请上传并填写参考信息，请填写需要合成的目标文本和语种模式",
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
