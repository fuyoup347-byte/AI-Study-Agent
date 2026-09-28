import streamlit as st
from openai import OpenAI
import os
import io

st.set_page_config(
    page_title="微电子专业 AI 学习助手",
    page_icon="🔬",
    layout="wide"
)

api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    st.error("⚠️ 尚未配置 DEEPSEEK_API_KEY，请在 Streamlit Secrets 中配置。")
    st.stop()

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

courses = [
    "电磁场与电磁波", "半导体物理", "模拟电子技术", "数字电子技术",
    "信号与系统", "微电子器件", "集成电路基础", "其他课程"
]
modes = ["教我知识点", "帮我解题", "考试复习", "错题分析", "资料问答"]

for key, default in {
    "course": courses[0], "mode": modes[0], "messages": [],
    "documents": [], "wrong_questions": [], "last_qa": None,
    "quiz": None, "summary": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def extract_text(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            return f"[PDF 读取失败：{e}]"
    if name.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"[Word 读取失败：{e}]"
    return "[暂不支持此文件格式]"

def build_document_context():
    if not st.session_state.documents:
        return ""
    parts, used = [], 0
    max_total = 45000
    for doc in st.session_state.documents:
        remaining = max_total - used
        if remaining <= 0:
            break
        snippet = doc["text"][:remaining]
        parts.append(f"\n===== 学习资料：{doc['name']} =====\n{snippet}")
        used += len(snippet)
    return "".join(parts)

def ask_ai(prompt, system_prompt=None, temperature=0.4):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(st.session_state.messages[-12:])
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=temperature
    )
    return response.choices[0].message.content

def save_wrong_question(question, answer):
    item = {
        "course": st.session_state.course,
        "question": question,
        "answer": answer
    }
    if not any(x["question"] == question for x in st.session_state.wrong_questions):
        st.session_state.wrong_questions.append(item)

system_prompt = f"""
你是一名优秀的大学微电子专业 AI 学习老师。
当前课程：{st.session_state.course}
当前模式：{st.session_state.mode}

请全程使用中文，面向大学本科微电子专业学生教学。
不要只给答案，要真正把学生教会。
基础不足时先补基础；解释概念时说明“是什么、为什么、怎么用”。
解题必须展示思路、已知条件、公式、推导、计算和答案检查。
数学公式使用 LaTeX：行内 $...$，独立公式 $$...$$。
不要使用 Unicode 特殊数学字符代替 LaTeX。
解释公式中每个符号的意义和单位。
发现错误时明确指出错误原因。
如果依据上传资料回答，应优先依据资料；资料不足时明确说明。
"""

with st.sidebar:
    st.header("📚 学习设置")
    st.session_state.course = st.selectbox(
        "选择课程", courses, index=courses.index(st.session_state.course)
    )
    st.session_state.mode = st.selectbox(
        "学习模式", modes, index=modes.index(st.session_state.mode)
    )
    st.divider()
    st.write(f"**课程：** {st.session_state.course}")
    st.write(f"**资料：** {len(st.session_state.documents)} 份")
    st.write(f"**错题：** {len(st.session_state.wrong_questions)} 道")
    if st.button("🗑️ 清空当前对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_qa = None
        st.rerun()
    if st.button("♻️ 清空所有资料", use_container_width=True):
        st.session_state.documents = []
        st.rerun()

st.title("🔬 微电子专业 AI 学习助手")
st.caption("Powered by DeepSeek · 多课程 · 资料问答 · 解题 · 错题本 · 自动出题 · 知识框架")

tabs = st.tabs(["💬 AI 老师", "📚 学习资料", "📝 自动出题", "❌ 错题本", "🧠 知识框架"])

with tabs[0]:
    st.subheader(f"正在学习：{st.session_state.course}")
    if st.session_state.documents:
        st.info(f"已加载 {len(st.session_state.documents)} 份资料，可直接问“根据我上传的资料讲解……”")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input(f"请输入关于「{st.session_state.course}」的问题……")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state.messages.append({"role": "user", "content": question})

        prompt = question
        context = build_document_context()
        if context:
            prompt += f"\n\n以下是学生上传的学习资料，请优先根据资料回答：\n{context}"

        with st.chat_message("assistant"):
            with st.spinner("AI 老师正在思考……"):
                try:
                    answer = ask_ai(prompt, system_prompt)
                except Exception as e:
                    answer = f"⚠️ AI 请求失败：{e}"
            st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.last_qa = {"question": question, "answer": answer}
        st.rerun()

    if st.session_state.last_qa:
        if st.button("❌ 把这道题加入错题本", use_container_width=True):
            save_wrong_question(
                st.session_state.last_qa["question"],
                st.session_state.last_qa["answer"]
            )
            st.success("已加入错题本！")
            st.rerun()

with tabs[1]:
    st.subheader("📚 上传你的学习资料")
    uploaded = st.file_uploader(
        "支持 PDF / Word / TXT / Markdown",
        type=["pdf", "docx", "txt", "md", "markdown"],
        accept_multiple_files=True
    )
    if uploaded:
        for file in uploaded:
            if not any(d["name"] == file.name for d in st.session_state.documents):
                st.session_state.documents.append({
                    "name": file.name,
                    "text": extract_text(file)
                })
        st.success(f"已加载 {len(uploaded)} 个文件。")
        st.rerun()

    for i, doc in enumerate(st.session_state.documents):
        with st.expander(f"📄 {doc['name']}"):
            st.write(f"文本长度：{len(doc['text'])} 字符")
            st.text(doc["text"][:3000])
            if st.button("删除", key=f"delete_doc_{i}"):
                st.session_state.documents.pop(i)
                st.rerun()

    if st.session_state.documents:
        st.divider()
        st.markdown("### 🤖 资料智能处理")
        c1, c2, c3 = st.columns(3)
        context = build_document_context()

        with c1:
            if st.button("📖 总结资料", use_container_width=True):
                with st.spinner("正在总结……"):
                    try:
                        st.session_state.summary = ask_ai(
                            f"""请总结以下学习资料，输出：
1. 内容概览
2. 核心知识点
3. 必须记住的公式/定义
4. 容易混淆的地方
5. 考试可能出现的题型

资料：
{context}""", system_prompt)
                    except Exception as e:
                        st.error(f"处理失败：{e}")

        with c2:
            if st.button("🧠 提取重点", use_container_width=True):
                with st.spinner("正在提取重点……"):
                    try:
                        st.session_state.summary = ask_ai(
                            f"请从以下资料中提取最重要的知识点，并按“必须掌握 / 理解即可 / 易错点”分类。\n\n{context}",
                            system_prompt)
                    except Exception as e:
                        st.error(f"处理失败：{e}")

        with c3:
            if st.button("🎴 生成闪卡", use_container_width=True):
                with st.spinner("正在生成闪卡……"):
                    try:
                        st.session_state.summary = ask_ai(
                            f"请根据以下学习资料生成 10 张复习闪卡，每张包含“问题”和“答案”。\n\n{context}",
                            system_prompt)
                    except Exception as e:
                        st.error(f"处理失败：{e}")

        if st.session_state.summary:
            st.divider()
            st.markdown(st.session_state.summary)

with tabs[2]:
    st.subheader("📝 自动练习题")
    difficulty = st.select_slider("难度", options=["基础", "中等", "较难", "考试压轴"], value="中等")
    num_questions = st.slider("题目数量", 3, 10, 5)
    topic = st.text_input("指定知识点（可留空）", placeholder="例如：麦克斯韦方程组、PN结、放大电路……")

    if st.button("🚀 生成练习题", type="primary"):
        context = build_document_context()
        prompt = f"""
请为大学微电子专业学生生成 {num_questions} 道{difficulty}难度的练习题。
课程：{st.session_state.course}
知识点：{topic or "综合"}
要求：覆盖核心知识；可包含选择题、计算题、概念题；每题给标准答案和详细解析。
如果有上传资料，优先根据资料出题。

资料：
{context}
"""
        with st.spinner("正在生成题目……"):
            try:
                st.session_state.quiz = ask_ai(prompt, system_prompt)
            except Exception as e:
                st.error(f"出题失败：{e}")

    if st.session_state.quiz:
        st.divider()
        st.markdown(st.session_state.quiz)

with tabs[3]:
    st.subheader("❌ 我的错题本")
    if not st.session_state.wrong_questions:
        st.info("还没有错题。做题后点击“加入错题本”即可保存。")
    else:
        for i, item in enumerate(st.session_state.wrong_questions):
            with st.expander(f"{i + 1}. [{item['course']}] {item['question'][:80]}"):
                st.markdown("**题目：**")
                st.markdown(item["question"])
                st.markdown("**AI 分析：**")
                st.markdown(item["answer"])
                if st.button("🗑️ 删除", key=f"wrong_{i}"):
                    st.session_state.wrong_questions.pop(i)
                    st.rerun()

        if st.button("🧠 分析我的薄弱点", use_container_width=True):
            wrong_text = "\n\n".join(
                f"题目：{x['question']}\n分析：{x['answer']}"
                for x in st.session_state.wrong_questions
            )
            with st.spinner("正在分析薄弱点……"):
                try:
                    result = ask_ai(
                        f"""根据下面的错题记录，分析学生的薄弱知识点。
输出：1. 高频错误类型 2. 薄弱知识点 3. 为什么容易错 4. 建议复习顺序 5. 3 道针对性训练题

{wrong_text}""",
                        system_prompt
                    )
                    st.markdown(result)
                except Exception as e:
                    st.error(f"分析失败：{e}")

with tabs[4]:
    st.subheader("🧠 知识框架 / 考试重点")
    framework_topic = st.text_input(
        "知识点或章节",
        placeholder="例如：电磁场与电磁波 第一章 矢量分析"
    )
    if st.button("生成知识框架", type="primary"):
        context = build_document_context()
        with st.spinner("正在构建知识框架……"):
            try:
                result = ask_ai(
                    f"""请为“{framework_topic or st.session_state.course}”建立本科微电子专业学习框架。
要求：
1. 从基础概念到高级概念逐层展开。
2. 标出必须掌握的内容。
3. 标出常见易错点。
4. 列出核心公式。
5. 给出知识点之间的联系。
6. 最后给出考试复习路线。

参考资料：
{context}""",
                    system_prompt
                )
                st.markdown(result)
            except Exception as e:
                st.error(f"生成失败：{e}")

st.divider()
st.caption("🔒 API Key 仅通过 Streamlit Secrets 读取，不写入代码。")
