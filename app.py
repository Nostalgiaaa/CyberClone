import chainlit as cl
from langchain_community.llms import Ollama
import re  # 正则表达式有时可以帮助更复杂的解析，但这里我们先用字符串查找

# --- 配置 ---
OLLAMA_MODEL_NAME = "qwen3:14b"  # 您在 Ollama 中部署的模型名
OLLAMA_BASE_URL = "http://localhost:11434"  # 您的 Ollama 服务地址

# --- 初始化 LangChain 组件 ---
llm = Ollama(
    model=OLLAMA_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
)

# 简单的提示模板，期望模型在回复中自然包含 <think>...</think> 标签
# 您可能需要根据您的模型调整此提示，以确保它能按预期工作
prompt_template_str = """用户: {user_message}
AI: """


@cl.on_chat_start
async def start_chat():
    cl.user_session.set("llm", llm)
    await cl.Message(
        content=f"你好！我是基于 **{OLLAMA_MODEL_NAME}** 模型的AI助手。请问有什么可以帮您的吗？"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    user_message_content = message.content
    current_llm = cl.user_session.get("llm")

    final_prompt = prompt_template_str.format(user_message=user_message_content)

    # ---- 初始化 Chainlit UI 元素 ----
    # 1. 创建 "AI 思考过程" 的步骤 UI，初始内容为空
    #    这个 step 的 output 会在解析到完整的 <think>...</think> 内容后更新
    async with cl.Step(name="AI 思考过程", show_input=False) as think_step:
        think_step.output = ""  # 先设置为空，或者 "正在思考..."

        # 2. 创建最终回复的空消息 UI，用于流式填充
        final_reply_msg = cl.Message(content="")
        await final_reply_msg.send()  # 必须先发送空壳

        # ---- 变量用于流式解析 ----
        accumulated_think_content = ""  # 用于累积 <think> 标签内的内容
        current_processing_buffer = ""  # 用于处理跨 token 的标签
        is_inside_think_block = False  # 当前是否正在解析 <think> 标签内的内容

        try:
            print(f"DEBUG: Sending prompt to LLM: '{final_prompt[:300]}...'")

            async for token in current_llm.astream(final_prompt):
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
                    await final_reply_msg.stream_token(current_processing_buffer)
                else:  # 如果流结束时仍在 think 块内（标签不完整）
                    # print(f"DEBUG: Appending remaining buffer to think content: '{current_processing_buffer}'")
                    accumulated_think_content += current_processing_buffer
                    think_step.output = accumulated_think_content  # 更新最后的思考内容

            # 最终检查和设置默认值
            if not think_step.output or think_step.output == "正在生成思考计划...":
                think_step.output = "(模型未提供明确的思考过程标签内容)"

            if not final_reply_msg.content.strip():
                await final_reply_msg.update()

            print("DEBUG: Stream processing complete.")

        except Exception as e:
            error_msg = f"处理流时出错: {str(e)}"
            print(f"ERROR: Exception during stream processing: {error_msg}")
            if final_reply_msg and final_reply_msg.id:
                await final_reply_msg.update()
            else:
                await cl.Message(content=error_msg).send()
            if think_step and think_step.id:  # 更新step的错误信息
                think_step.output = error_msg
