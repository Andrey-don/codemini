import os
import re

# Корень проекта codemini — папка codemini/
CODEMINI_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_project_file(filename: str) -> str:
    path = os.path.join(CODEMINI_ROOT, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


USED_TOPICS_FILE = os.path.join(CODEMINI_ROOT, "used-topics.txt")


def get_used_topics() -> set:
    if not os.path.exists(USED_TOPICS_FILE):
        return set()
    with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


def mark_topic_used(topic: str) -> None:
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(topic.strip() + "\n")


CONTENT_PLAN_FILE = os.path.join(CODEMINI_ROOT, "content-plan.md")


def append_topics_to_plan(topics: list) -> None:
    with open(CONTENT_PLAN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    by_section: dict = {}
    for section, topic in topics:
        by_section.setdefault(section, []).append(topic)

    numbers = re.findall(r"^(\d+)\.", content, re.MULTILINE)
    next_num = max((int(n) for n in numbers), default=0) + 1

    lines_to_add = []
    for section, section_topics in by_section.items():
        if f"### {section}" not in content:
            lines_to_add.append(f"\n### {section}")
        else:
            lines_to_add.append(f"\n### {section} (дополнение)")
        for topic in section_topics:
            lines_to_add.append(f"{next_num}. {topic}")
            next_num += 1

    if lines_to_add:
        with open(CONTENT_PLAN_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(lines_to_add) + "\n")


def save_article(filename: str, content: str) -> str:
    articles_path = os.path.join(CODEMINI_ROOT, "articles")
    os.makedirs(articles_path, exist_ok=True)
    filepath = os.path.join(articles_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
