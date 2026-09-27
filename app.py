import streamlit as st
from openai import OpenAI
import os

# =========================
# 页面设置
# =========================

st.set_page_config(
    page_title="微电子专业 AI 学习助手",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 微电子专业 AI 学习助手")
st.caption("Powered by DeepSeek")


# =========================
# DeepSeek
# =========================

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)


# =========================
# 课程列表
# =========================

courses = [
    "电磁场与电磁波",
    "半导体物理",
    "模拟电子技术",
    "数字电子技术",
    "信号与系统",
    "微电子器件",
    "集成电路基础",
    "其他课程"
]


# =========================
# 学习模式
# =========================

modes = [
    "教我知识点",
    "帮我解题",
    "考试复习",
    "错题分析"
]


# =========================
# 侧边栏
# =========================

with st.sidebar:

    st.header("📚 学习设置")

    course = st.selectbox(
        "选择课程",
        courses
    )

    mode = st.selectbox(
        "学习模式",
        modes
    )

    st.divider()

    st.write("### 当前学习")

    st.write(f"**课程：** {course}")
    st.write(f"**模式：** {mode}")

    st.divider()

    if st.button("🗑️ 清空聊天记录"):

        st.session_state.messages = [
            {
                "role": "system",
                "content": ""
            }
        ]

        st.rerun()


# =========================
# 构建 AI 老师提示词
# =========================

system_prompt = f"""
你是一名优秀的大学微电子专业 AI 学习老师。

学生目前正在学习：

课程：
{course}

学习模式：
{mode}

你的任务是帮助学生真正理解知识，而不是简单给出答案。

教学原则：

1. 使用中文回答。
2. 根据大学本科微电子专业的学习水平进行讲解。
3. 如果学生基础不足，先补充必要的基础知识。
4. 解释概念时，要说明“是什么、为什么、怎么用”。
5. 解题时不要直接跳到答案，要展示推导过程。
6. 每一步都说明为什么这样做。
7. 涉及公式时，必须使用 LaTeX。
8. 行内公式使用 $...$。
9. 独立公式使用 $$...$$。
10. 不要使用 Unicode 特殊数学字符代替 LaTeX。
11. 涉及物理量时，要解释每个符号的含义和单位。
12. 如果学生理解错误，要明确指出错误，并解释为什么。
13. 如果题目存在多种解法，可以比较不同方法。
14. 如果学生的问题比较简单，也要认真回答，不要敷衍。

当前学习模式的要求：

如果是“教我知识点”：
- 从基础开始。
- 建立知识体系。
- 用直观例子帮助理解。
- 最后给学生一个小问题检查理解。

如果是“帮我解题”：
- 先分析题目。
- 列出已知条件。
- 明确要求什么。
- 选择公式或方法。
- 分步骤计算。
- 最后检查答案。

如果是“考试复习”：
- 总结重点。
- 区分必须掌握和容易混淆的知识。
- 给出典型题型。
- 最后进行小测验。

如果是“错题分析”：
- 分析学生错在哪里。
- 判断属于概念错误、公式错误、计算错误还是思路错误。
- 给出正确思路。
- 最后给一道类似题帮助学生巩固。

你不是只负责回答问题，而是负责把学生教会。
"""


# =========================
# 聊天记录
# =========================

if "messages" not in st.session_state:

    st.session_state.messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

else:

    # 更新 system prompt
    st.session_state.messages[0]["content"] = system_prompt


# =========================
# 显示聊天记录
# =========================

for message in st.session_state.messages:

    if message["role"] != "system":

        with st.chat_message(message["role"]):

            st.markdown(message["content"])


# =========================
# 输入框
# =========================

question = st.chat_input(
    f"请输入关于「{course}」的问题……"
)


# =========================
# AI 回答
# =========================

if question:

    # 显示用户问题

    with st.chat_message("user"):

        st.markdown(question)

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question
        }
    )


    # 请求 DeepSeek

    with st.chat_message("assistant"):

        with st.spinner("正在思考……"):

            try:

                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=st.session_state.messages
                )

                answer = response.choices[0].message.content

            except Exception as e:

                answer = f"⚠️ 出现错误：{e}"

        st.markdown(answer)


    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )
