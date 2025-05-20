document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    // 后端流式 API 地址
    const API_STREAM_URL = 'http://localhost:8000/chat'; // 确保这与您的 FastAPI 端点一致

    /**
     * 将用户消息添加到聊天框
     * @param {string} message - 消息内容
     * @param {string} sender - 发送者 ('user' 或 'ai')
     */
    function addUserMessageToChatBox(message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', 'user-message');
        messageElement.textContent = message;
        chatBox.appendChild(messageElement);
        scrollToBottom();
    }

    /**
     * 为 AI 的回复（包括思考过程和最终回复）创建并添加 DOM 元素框架
     * @param {string} initialReplyText - AI 回复区域的初始文本 (例如 "AI 正在思考...")
     * @returns {object} 包含对回复元素、思考过程元素和切换按钮的引用
     */
    function addAiMessagePod() {
        const messageContainer = document.createElement('div');
        messageContainer.classList.add('message', 'ai-message');

        // AI 回复部分
        const replyElement = document.createElement('div');
        replyElement.classList.add('ai-reply');
        replyElement.textContent = "AI 正在思考..."; // 初始提示
        messageContainer.appendChild(replyElement);

        // “查看/收起思考过程” 按钮容器 (初始隐藏)
        const thinkToggleContainer = document.createElement('div');
        thinkToggleContainer.classList.add('think-toggle-container');
        thinkToggleContainer.style.display = 'none'; // 只有当有思考过程时才显示

        const toggleButton = document.createElement('button');
        toggleButton.classList.add('think-toggle-button');
        toggleButton.textContent = '查看思考过程';
        thinkToggleContainer.appendChild(toggleButton);
        messageContainer.appendChild(thinkToggleContainer);

        // 思考过程区域 (初始隐藏)
        const thinkProcessElement = document.createElement('div');
        thinkProcessElement.classList.add('think-process');
        thinkProcessElement.style.display = 'none';

        const thinkTitle = document.createElement('strong');
        thinkTitle.textContent = '思考过程:';
        thinkProcessElement.appendChild(thinkTitle);

        const thinkContent = document.createElement('pre'); // 使用 <pre> 保留格式
        thinkProcessElement.appendChild(thinkContent);
        
        messageContainer.appendChild(thinkProcessElement);

        // 点击按钮的事件监听
        toggleButton.addEventListener('click', () => {
            const isHidden = thinkProcessElement.style.display === 'none';
            thinkProcessElement.style.display = isHidden ? 'block' : 'none';
            toggleButton.textContent = isHidden ? '收起思考过程' : '查看思考过程';
            scrollToBottom(); // 展开/收起时可能需要重新滚动
        });

        chatBox.appendChild(messageContainer);
        scrollToBottom();

        return {
            replyElement,          // 用于更新最终回复
            thinkToggleContainer,  // 用于控制按钮容器的显示
            thinkContentElement: thinkContent, // 用于填充思考过程文本
            messageContainer       // 整个 AI 消息的容器
        };
    }

    /**
     * 发送消息到后端并处理流式响应
     */
    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (messageText === '') return;

        addUserMessageToChatBox(messageText);
        userInput.value = ''; // 清空输入框

        // 为 AI 的回复创建 DOM 元素占位符
        const aiElements = addAiMessagePod();
        let firstReplyTokenReceived = false;

        try {
            const response = await fetch(API_STREAM_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream' // 明确希望接收 SSE
                },
                body: JSON.stringify({ message: messageText }),
            });

            if (!response.ok) {
                // 尝试从响应体中读取更详细的错误信息
                let errorDetail = `HTTP error ${response.status}`;
                try {
                    const errorData = await response.json(); // FastAPI 错误通常是 JSON
                    errorDetail = errorData.detail || JSON.stringify(errorData);
                } catch (e) {
                    // 如果响应不是JSON，或者没有body，使用状态文本
                    errorDetail = response.statusText || errorDetail;
                }
                throw new Error(errorDetail);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    // console.log("Stream finished by 'done' signal.");
                    break;
                }
                
                buffer += decoder.decode(value, { stream: true });

                // 按 Server-Sent Events 的格式处理 buffer 中的消息
                // 每个消息以 "data: " 开头，以 "\n\n" 结尾
                let endOfMessageIndex;
                while ((endOfMessageIndex = buffer.indexOf('\n\n')) >= 0) {
                    const messageLine = buffer.substring(0, endOfMessageIndex);
                    buffer = buffer.substring(endOfMessageIndex + 2); // 移除已处理的消息和两个换行符

                    if (messageLine.startsWith('data: ')) {
                        const jsonDataString = messageLine.substring(5).trim(); // 移除 "data: "
                        if (jsonDataString) {
                            try {
                                const eventData = JSON.parse(jsonDataString);
                                // console.log("Received event:", eventData);

                                if (eventData.type === 'think_process') {
                                    aiElements.thinkContentElement.textContent = eventData.content;
                                    if (eventData.content && eventData.content.trim() !== "") {
                                        aiElements.thinkToggleContainer.style.display = 'block'; // 显示“查看思考过程”按钮
                                    }
                                    // 如果此时 "AI 正在思考..." 还在，并且没有收到回复 token，可以不清空，等待第一个 reply_token 清空
                                } else if (eventData.type === 'reply_token') {
                                    if (!firstReplyTokenReceived) {
                                        aiElements.replyElement.textContent = ""; // 清空 "AI 正在思考..."
                                        firstReplyTokenReceived = true;
                                    }
                                    aiElements.replyElement.textContent += eventData.content;
                                    scrollToBottom();
                                } else if (eventData.type === 'error') {
                                    console.error("Error message from stream:", eventData.content);
                                    aiElements.replyElement.textContent = `错误: ${eventData.content}`;
                                    if (reader) await reader.cancel(); // 出错则停止读取
                                    return;
                                } else if (eventData.type === 'stream_end') {
                                    console.log("Stream ended by 'stream_end' signal.");
                                    if (reader) await reader.cancel();
                                    return;
                                }
                            } catch (e) {
                                console.error("Error parsing JSON from stream chunk:", e, "Chunk:", jsonDataString);
                            }
                        }
                    }
                }
            }
            // 处理可能残留在 buffer 中的最后一条不完整的消息 (如果流异常结束)
            if (buffer.startsWith('data: ')) {
                const jsonDataString = buffer.substring(5).trim();
                 if (jsonDataString) {
                    try {
                        const eventData = JSON.parse(jsonDataString);
                         if (eventData.type === 'reply_token') {
                            if (!firstReplyTokenReceived) {
                                aiElements.replyElement.textContent = "";
                                firstReplyTokenReceived = true;
                            }
                            aiElements.replyElement.textContent += eventData.content;
                        }
                        // 这里可以根据需要处理其他类型的最后消息
                    } catch (e) {
                        console.error("Error parsing JSON from final buffer:", e, "Data:", jsonDataString);
                    }
                 }
            }


        } catch (error) {
            console.error('发送或处理流式消息失败:', error);
            aiElements.replyElement.textContent = `通信错误: ${error.message}`;
        } finally {
            scrollToBottom();
        }
    }

    function scrollToBottom() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter' && !event.shiftKey) { // Shift+Enter 通常用于换行
            event.preventDefault(); // 阻止默认的回车换行行为
            sendMessage();
        }
    });

    // 初始加载时为AI的问候语（如果HTML中没有的话）添加一个简单的非流式pod
    // const initialAiMessage = chatBox.querySelector('.ai-message');
    // if (!initialAiMessage || chatBox.children.length === 0) {
    //     const elements = addAiMessagePod();
    //     elements.replyElement.textContent = "你好！我是AI助手，有什么可以帮你的吗？";
    //     // 对于初始消息，通常没有思考过程，所以不需要显示切换按钮
    //     elements.thinkToggleContainer.style.display = 'none';
    // }
});