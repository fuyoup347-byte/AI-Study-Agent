"""Import an existing study_agent_data.json into the mobile app database."""
import hashlib
import json
import sys
from pathlib import Path

from main import connect_db, utc_now


def import_data(source: Path):
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object from the previous Streamlit app.")
    now = utc_now()
    counts = {"documents": 0, "messages": 0, "wrong_questions": 0, "progress": 0}
    with connect_db() as db:
        for document in data.get("documents", []):
            name = str(document.get("name", "学习资料"))
            text = str(document.get("text", ""))
            if not text.strip():
                continue
            doc_id = document.get("id") or hashlib.sha256(f"{name}\0{text}".encode("utf-8")).hexdigest()
            result = db.execute("INSERT OR IGNORE INTO documents(id, name, text, created_at) VALUES (?, ?, ?, ?)",
                                (doc_id, name, text, now))
            counts["documents"] += result.rowcount
        for message in data.get("messages", []):
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            db.execute("INSERT INTO messages(role, content, course, created_at) VALUES (?, ?, ?, ?)",
                       (role, str(message.get("content", "")), "其他课程", now))
            counts["messages"] += 1
        for item in data.get("wrong_questions", []):
            result = db.execute("INSERT OR IGNORE INTO wrong_questions(course, question, answer, created_at) VALUES (?, ?, ?, ?)",
                                (str(item.get("course", "其他课程")), str(item.get("question", "")), str(item.get("answer", "")), now))
            counts["wrong_questions"] += result.rowcount
        for item in data.get("progress", []):
            db.execute("INSERT INTO progress(course, activity, title, details, created_at) VALUES (?, ?, ?, ?, ?)",
                       (str(item.get("course", "其他课程")), str(item.get("activity", "学习")),
                        str(item.get("title", "")), "", str(item.get("timestamp", now))))
            counts["progress"] += 1
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python import_local_data.py path\\to\\study_agent_data.json")
    imported = import_data(Path(sys.argv[1]))
    print("Imported: " + ", ".join(f"{key}={value}" for key, value in imported.items()))
