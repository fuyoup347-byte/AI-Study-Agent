import base64
import hashlib
import hmac
import io
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from docx import Document
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))
APP_USERNAME = os.getenv("APP_USERNAME", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./data/study_agent.sqlite3")).resolve()
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
STOP_CHARS = set("的了是在和与就都也不一个这那有上下中没我们你们他们她它，。、！？：；\"'（）()[]{}<>")

app = FastAPI(title="微电子学习助手 API", version="1.0.0")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    with connect_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                course TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course TEXT NOT NULL,
                activity TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wrong_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(course, question)
            );
        """)


init_db()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(username: str) -> str:
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode())
    signed = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(JWT_SECRET.encode(), signed, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def current_user(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录。")
    token = authorization[7:]
    try:
        header, payload, signature = token.split(".")
        signed = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(JWT_SECRET.encode(), signed, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(_unb64(payload))
        if claims["exp"] < time.time() or claims["sub"] != APP_USERNAME:
            raise ValueError("expired or invalid subject")
        return claims["sub"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录。") from exc


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    course: str = Field(default="半导体物理", max_length=100)
    mode: str = Field(default="教我知识点", max_length=100)
    temperature: float = Field(default=0.4, ge=0, le=1)


class QuizRequest(BaseModel):
    course: str = Field(default="半导体物理", max_length=100)
    topic: str = Field(default="", max_length=300)
    difficulty: str = Field(default="中等", max_length=30)
    count: int = Field(default=5, ge=3, le=10)


class WrongQuestionRequest(BaseModel):
    course: str = Field(max_length=100)
    question: str = Field(min_length=1, max_length=10000)
    answer: str = Field(min_length=1, max_length=30000)


class StudyToolRequest(BaseModel):
    action: str = Field(pattern="^(summary|key_points|flashcards|framework|weak_points)$")
    course: str = Field(default="半导体物理", max_length=100)
    topic: str = Field(default="", max_length=300)


def require_login_config():
    if not APP_USERNAME or not APP_PASSWORD or len(JWT_SECRET) < 32:
        raise HTTPException(status_code=503, detail="服务端登录配置不完整。")


def ai_client():
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="服务端尚未配置 DeepSeek API Key。")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com", timeout=60, max_retries=2)


def record_progress(db, course: str, activity: str, title: str, details: str = ""):
    db.execute(
        "INSERT INTO progress(course, activity, title, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (course, activity, title[:200], details, utc_now()),
    )


def extract_text(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    try:
        if suffix in {".txt", ".md", ".markdown"}:
            text = data.decode("utf-8-sig", errors="replace")
        elif suffix == ".pdf":
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        elif suffix == ".docx":
            text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
        else:
            raise HTTPException(status_code=415, detail="仅支持 PDF、DOCX、TXT 和 Markdown。")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{name} 解析失败：{exc}") from exc
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"{name} 没有可提取的文字；扫描版 PDF 需要先做 OCR。")
    if len(text) > 2_000_000:
        raise HTTPException(status_code=413, detail=f"{name} 提取文本过大（上限 200 万字符）。")
    return text


def retrieve_context(db, query: str, max_chars: int = 8000):
    docs = db.execute("SELECT name, text FROM documents ORDER BY created_at DESC").fetchall()
    if not docs:
        return ""
    q_chars = set(query) - STOP_CHARS
    chunks = []
    for doc in docs:
        text = doc["text"]
        pieces = [text[i:i + 1000] for i in range(0, len(text), 900)]
        for piece in pieces:
            score = len(q_chars & set(piece)) / max(len(q_chars), 1)
            if not query or score > 0:
                chunks.append((score, doc["name"], piece))
    chunks.sort(key=lambda item: item[0], reverse=True)
    selected, used = [], 0
    for _score, name, piece in chunks:
        if used >= max_chars:
            break
        piece = piece[:max_chars - used]
        selected.append(f"\n===== 学习资料：{name} =====\n{piece}")
        used += len(piece)
    return "".join(selected)


def system_prompt(course: str, mode: str):
    return f"""你是一名优秀的大学微电子专业 AI 学习老师。
当前课程：{course}
当前模式：{mode}
请使用中文教学，说明概念是什么、为什么、怎么用。解题展示思路、条件、公式、推导和检查。公式使用 LaTeX，并解释符号和单位。依据学习资料回答时优先引用资料；资料不足要明确说明。"""


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/login")
def login(body: LoginRequest):
    require_login_config()
    user_ok = hmac.compare_digest(body.username.encode(), APP_USERNAME.encode())
    pass_ok = hmac.compare_digest(body.password.encode(), APP_PASSWORD.encode())
    if not user_ok or not pass_ok:
        time.sleep(0.25)
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    return {"access_token": create_token(APP_USERNAME), "token_type": "bearer"}


@app.get("/me")
def me(user: str = Depends(current_user)):
    return {"username": user}


@app.get("/documents")
def list_documents(user: str = Depends(current_user)):
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT id, name, created_at FROM documents ORDER BY created_at DESC")]


@app.post("/documents")
async def upload_documents(files: list[UploadFile] = File(...), course: str = Form(default="其他课程"), user: str = Depends(current_user)):
    added, skipped = [], []
    with connect_db() as db:
        for file in files:
            data = await file.read(25 * 1024 * 1024 + 1)
            if len(data) > 25 * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"{file.filename} 超过 25 MB 限制。")
            text = extract_text(file.filename or "资料", data)
            digest = hashlib.sha256(data).hexdigest()
            exists = db.execute("SELECT 1 FROM documents WHERE id = ?", (digest,)).fetchone()
            if exists:
                skipped.append(file.filename)
                continue
            db.execute("INSERT INTO documents(id, name, text, created_at) VALUES (?, ?, ?, ?)",
                       (digest, file.filename or "学习资料", text, utc_now()))
            added.append(file.filename)
        if added:
            record_progress(db, course, "上传资料", f"新增 {len(added)} 份学习资料")
    return {"added": added, "skipped": skipped}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, user: str = Depends(current_user)):
    with connect_db() as db:
        cursor = db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到这份资料。")
    return {"ok": True}


@app.get("/messages")
def list_messages(limit: int = 100, course: str | None = None, user: str = Depends(current_user)):
    limit = min(max(limit, 1), 500)
    with connect_db() as db:
        if course:
            rows = db.execute("SELECT role, content, course, created_at FROM messages WHERE course = ? ORDER BY id DESC LIMIT ?", (course, limit)).fetchall()
        else:
            rows = db.execute("SELECT role, content, course, created_at FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return list(reversed([dict(row) for row in rows]))


@app.delete("/messages")
def clear_messages(user: str = Depends(current_user)):
    with connect_db() as db:
        db.execute("DELETE FROM messages")
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatRequest, user: str = Depends(current_user)):
    with connect_db() as db:
        history = db.execute("SELECT role, content FROM messages WHERE course = ? ORDER BY id DESC LIMIT 12", (body.course,)).fetchall()
        history = list(reversed([dict(row) for row in history]))
        context = retrieve_context(db, body.question)
    prompt = body.question
    if context:
        prompt += f"\n\n以下是学生上传的学习资料，请优先根据资料回答：\n{context}"
    try:
        response = ai_client().chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt(body.course, body.mode)}, *history,
                      {"role": "user", "content": prompt}],
            temperature=body.temperature,
        )
        answer = response.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 请求失败：{exc}") from exc
    with connect_db() as db:
        created = utc_now()
        db.executemany("INSERT INTO messages(role, content, course, created_at) VALUES (?, ?, ?, ?)", [
            ("user", body.question, body.course, created),
            ("assistant", answer, body.course, created),
        ])
        record_progress(db, body.course, "问答", body.question)
    return {"answer": answer, "created_at": created}


@app.post("/quiz")
def create_quiz(body: QuizRequest, user: str = Depends(current_user)):
    with connect_db() as db:
        context = retrieve_context(db, body.topic)
    prompt = f"""请为大学微电子专业学生生成 {body.count} 道{body.difficulty}难度的练习题。
课程：{body.course}；知识点：{body.topic or '综合'}。
可包含选择题、计算题、概念题，每题给标准答案和详细解析。若有资料请优先根据资料出题。
资料：\n{context}"""
    try:
        response = ai_client().chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt(body.course, "考试复习")}, {"role": "user", "content": prompt}],
            temperature=0.4,
        )
        result = response.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"出题失败：{exc}") from exc
    with connect_db() as db:
        record_progress(db, body.course, "练习", f"生成练习题：{body.topic or '综合'}（{body.count}题）", result)
    return {"quiz": result}


@app.get("/progress")
def get_progress(course: str | None = None, user: str = Depends(current_user)):
    with connect_db() as db:
        if course:
            rows = db.execute("SELECT * FROM progress WHERE course = ? ORDER BY id DESC LIMIT 500", (course,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM progress ORDER BY id DESC LIMIT 500").fetchall()
    return [dict(row) for row in rows]


@app.post("/study-tools")
def study_tool(body: StudyToolRequest, user: str = Depends(current_user)):
    with connect_db() as db:
        context = retrieve_context(db, body.topic)
        wrong = db.execute("SELECT course, question, answer FROM wrong_questions WHERE course = ? ORDER BY id DESC LIMIT 30", (body.course,)).fetchall()
    if body.action == "summary":
        title, activity, prompt = "总结已上传资料", "资料总结", f"请总结资料：1.内容概览 2.核心知识点 3.重要公式和定义 4.易混点 5.考试题型。\n\n资料：\n{context}"
    elif body.action == "key_points":
        title, activity, prompt = "提取资料重点", "重点提取", f"请从资料提取重点，分为“必须掌握 / 理解即可 / 易错点”。\n\n资料：\n{context}"
    elif body.action == "flashcards":
        title, activity, prompt = "生成复习闪卡", "闪卡", f"请根据资料生成 10 张复习闪卡，每张包含问题和答案。\n\n资料：\n{context}"
    elif body.action == "framework":
        title = f"知识框架：{body.topic or body.course}"
        activity = "知识框架"
        prompt = f"请为“{body.topic or body.course}”建立本科微电子学习框架，按基础到进阶组织，列必须掌握内容、易错点、核心公式、知识联系和考试复习路线。\n\n参考资料：\n{context}"
    else:
        title, activity = "分析错题薄弱点", "薄弱点分析"
        wrong_text = "\n\n".join(f"课程：{item['course']}\n题目：{item['question']}\n分析：{item['answer']}" for item in wrong)
        if not wrong_text:
            raise HTTPException(status_code=400, detail="错题本为空，请先保存几道错题。")
        prompt = f"根据错题分析学生薄弱点，输出高频错误、薄弱知识、易错原因、复习顺序和 3 道训练题。\n\n{wrong_text}"
    if not context and body.action in {"summary", "key_points", "flashcards"}:
        raise HTTPException(status_code=400, detail="请先上传学习资料。")
    try:
        response = ai_client().chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt(body.course, "考试复习")}, {"role": "user", "content": prompt}],
            temperature=0.3,
        )
        result = response.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"资料处理失败：{exc}") from exc
    with connect_db() as db:
        record_progress(db, body.course, activity, title, result[:30000])
    return {"result": result}


@app.get("/wrong-questions")
def list_wrong_questions(user: str = Depends(current_user)):
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM wrong_questions ORDER BY id DESC")]


@app.post("/wrong-questions")
def add_wrong_question(body: WrongQuestionRequest, user: str = Depends(current_user)):
    with connect_db() as db:
        db.execute("INSERT OR IGNORE INTO wrong_questions(course, question, answer, created_at) VALUES (?, ?, ?, ?)",
                   (body.course, body.question, body.answer, utc_now()))
    return {"ok": True}


@app.delete("/wrong-questions/{question_id}")
def delete_wrong_question(question_id: int, user: str = Depends(current_user)):
    with connect_db() as db:
        cursor = db.execute("DELETE FROM wrong_questions WHERE id = ?", (question_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到这道错题。")
    return {"ok": True}
