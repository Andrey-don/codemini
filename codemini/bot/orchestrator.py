import os
import re
import logging
import markdown as md_converter
from datetime import datetime
from codemini.bot.agents import researcher, writer, editor, seo, image_finder, topic_generator
from codemini.bot.utils.file_loader import (
    read_project_file, save_article, get_used_topics,
    mark_topic_used, append_topics_to_plan,
)
from codemini.bot.utils import wp_posts


def generate_article(topic: str, article_type: str = "обзор") -> dict:
    """Полный цикл: Ресёрчер → Писатель → Редактор → SEO → Сохранение"""

    print(f"[1/5] Ресёрчер собирает материал: {topic}")
    research = researcher.run(topic)

    print(f"[2/5] Писатель пишет статью ({article_type})...")
    draft = writer.run(topic, article_type, research)

    print(f"[3/5] Редактор правит...")
    edited = editor.run(draft)

    wp_categories = [c["name"] for c in wp_posts.get_categories() if c["name"] != "Без рубрики"]

    print(f"[4/5] Подбираем изображения из Unsplash...")
    edited, featured_media_id = image_finder.run(edited)

    print(f"[5/6] SEO-агент анализирует...")
    seo_draft = seo.run(edited, wp_categories or None)
    final = editor.run_seo_revision(edited, seo_draft)

    print(f"[6/6] Финальный SEO-анализ...")
    seo_data = seo.run(final, wp_categories or None)

    html_article = md_converter.markdown(final, extensions=["extra"])
    html_article = re.sub(r"<h1[^>]*>.*?</h1>", "", html_article, count=1, flags=re.IGNORECASE | re.DOTALL)
    html_article = re.sub(r"<p>\s*</p>", "", html_article)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_topic = "".join(c for c in topic if c.isalnum() or c in " -_")
    safe_topic = safe_topic.strip().replace(" ", "-")[:40] or "article"
    filename = f"{timestamp}_{safe_topic}.html"

    date_str = datetime.now().strftime("%d.%m.%Y")
    full_content = f"""<!--
==============================================
  ПУБЛИКАЦИЯ В WORDPRESS — codemini.ru
==============================================
  Тип статьи : {article_type}
  Дата       : {date_str}
----------------------------------------------
  SEO-ДАННЫЕ:
{seo_data}
==============================================
  КОД СТАТЬИ (вставить во вкладку "Код"):
==============================================
-->

{html_article}"""
    filepath = save_article(filename, full_content)
    mark_topic_used(topic)
    print(f"Статья сохранена: {filepath}")

    category_name = _parse_category(seo_data)
    category_id = _find_category_id(category_name) if category_name else None

    return {
        "topic": topic,
        "type": article_type,
        "article": html_article,
        "seo": seo_data,
        "title": (_parse_title(seo_data) or topic).capitalize(),
        "tags": _parse_tags(seo_data),
        "meta_description": _parse_meta_description(seo_data),
        "focus_keyword": _parse_focus_keyword(seo_data, (_parse_title(seo_data) or topic)),
        "slug": _parse_slug(seo_data),
        "category_id": category_id,
        "category_name": category_name,
        "featured_media_id": featured_media_id,
        "file": filepath,
    }


def _parse_title(seo_data: str) -> str:
    match = re.search(r"\*{0,2}Заголовок[^\n*]*\*{0,2}[^\n]*\n?\s*([^\n#*]{10,})", seo_data)
    if not match:
        return ""
    title = match.group(1).strip()
    return re.sub(r"^[—\-]\s*", "", title)


def _parse_tags(seo_data: str) -> list[str]:
    match = re.search(r"\*{0,2}Метки\*{0,2}[^\n]*\n?\s*([^\n#*]+)", seo_data)
    if not match:
        return []
    raw = re.sub(r"^[—-]\s*", "", match.group(1).strip())
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_meta_description(seo_data: str) -> str:
    match = re.search(r"\*{0,2}Meta Description\*{0,2}[^\n]*\n?\s*([^\n#*]{20,})", seo_data)
    if not match:
        return ""
    return re.sub(r"^[—\-]\s*", "", match.group(1).strip())


_GENERIC_KEYWORDS = {"сравнение", "обзор", "гайд", "курсы", "школа", "дети", "программирование", "онлайн", "обучение", "выбор"}


def _parse_focus_keyword(seo_data: str, title: str = "") -> str:
    kw = ""
    match = re.search(r"\*{0,2}Фокусное слово\*{0,2}[^\n]*\n?\s*([^\n#*]{2,30})", seo_data)
    if match:
        kw = re.sub(r"^[—\-]\s*", "", match.group(1).strip())
        kw = kw.split()[0] if kw else ""
    if not kw:
        match = re.search(r"\*{0,2}Ключевые слова\*{0,2}[^\n]*\n\s*[-*]?\s*([^\n#*]{3,})", seo_data)
        if match:
            kw = re.sub(r"^[—\-]\s*", "", match.group(1).strip())
            kw = kw.split()[0] if kw else ""
    # Если слово слишком общее — берём первое слово заголовка
    if not kw or kw.lower() in _GENERIC_KEYWORDS:
        if title:
            first = title.split()[0].strip("«»\"':,.")
            if first:
                return first
    return kw


def _parse_slug(seo_data: str) -> str:
    match = re.search(r"\*{0,2}Slug[^\n*]*\*{0,2}[^\n]*\n?\s*[`\"]?([a-z0-9][a-z0-9\-]{3,})[`\"]?", seo_data)
    return match.group(1).strip() if match else ""


def _parse_category(seo_data: str) -> str:
    match = re.search(r"\*{0,2}Рубрика\*{0,2}[^\n]*\n?\s*\*{0,2}([^\n#*\(]{3,})\*{0,2}", seo_data)
    if not match:
        return ""
    return re.sub(r"^[—\-]\s*", "", match.group(1).strip())


def _find_category_id(category_name: str) -> int | None:
    from difflib import SequenceMatcher
    categories = wp_posts.get_categories()
    if not categories:
        return None
    name_lower = category_name.lower().strip()
    for cat in categories:
        if cat["name"].lower().strip() == name_lower:
            return cat["id"]
    best_id, best_score = None, 0.0
    for cat in categories:
        score = SequenceMatcher(None, name_lower, cat["name"].lower().strip()).ratio()
        if score > best_score:
            best_score, best_id = score, cat["id"]
    return best_id if best_score >= 0.6 else None


def get_schedule_topics(start_date: str, days: int = 10) -> list[dict]:
    from datetime import datetime, timedelta

    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            start = datetime.strptime(start_date.strip(), fmt)
            if fmt == "%d.%m":
                start = start.replace(year=datetime.now().year)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Не могу распознать дату: {start_date}. Напиши в формате ДД.ММ")

    plan_text = read_project_file("content-plan.md")
    sections = {}
    current_section = None
    for line in plan_text.splitlines():
        if line.startswith("### "):
            current_section = line[4:].strip()
            sections[current_section] = []
        elif line.startswith("## ") or line.startswith("# "):
            current_section = None
        elif current_section and re.match(r"^\d+\.\s+", line):
            topic = re.sub(r"^\d+\.\s+", "", line).strip()
            sections[current_section].append(topic)

    section_names = [s for s, topics in sections.items() if topics]
    used = get_used_topics()
    type_cycle = ["обзор", "гайд", "сравнение", "обзор", "гайд", "обзор"]

    from difflib import SequenceMatcher
    wp_titles = wp_posts.get_post_titles()

    _STOP_WORDS = {"и", "в", "на", "что", "как", "это", "она", "он", "а", "но", "то",
                   "из", "по", "за", "или", "же", "ни", "не", "от", "до", "при"}

    def _key_words(text: str) -> set:
        words = re.sub(r"[^\w\s]", " ", text.lower()).split()
        return {w[:5] for w in words if len(w) >= 4 and w not in _STOP_WORDS}

    def _is_wp_duplicate(topic: str) -> bool:
        t_words = _key_words(topic)
        for title in wp_titles:
            if t_words and len(t_words & _key_words(title)) >= 2:
                return True
            if SequenceMatcher(None, topic.lower(), title).ratio() >= 0.55:
                return True
        return False

    available = {s: [t for t in topics if t.lower() not in used and not _is_wp_duplicate(t)]
                 for s, topics in sections.items() if topics}

    total_available = sum(len(v) for v in available.values())
    if total_available < 10:
        print(f"[topic_generator] Осталось {total_available} тем. Генерирую новые...")
        all_used = list(used) + [t for sec in sections.values() for t in sec]
        new_topics_raw = topic_generator.run(
            used_topics=all_used, sections=section_names, topics_per_section=10,
        )
        new_topics = _parse_generated_topics(new_topics_raw)
        if new_topics:
            append_topics_to_plan(new_topics)
            for section, topic in new_topics:
                if topic.lower() not in used and not _is_wp_duplicate(topic):
                    available.setdefault(section, []).append(topic)
                    if section not in section_names:
                        section_names.append(section)

    schedule = []
    sec_idx = 0
    day_offset = 0
    while len(schedule) < days:
        section = section_names[sec_idx % len(section_names)]
        topics_left = available.get(section, [])
        if topics_left:
            topic = topics_left.pop(0)
            day = start.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
            schedule.append({
                "topic": topic,
                "article_type": type_cycle[day_offset % len(type_cycle)],
                "publish_date": day.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            day_offset += 1
        sec_idx += 1
        if sec_idx > len(section_names) * 100:
            break

    return schedule


def _parse_generated_topics(raw: str) -> list[tuple[str, str]]:
    result = []
    current_section = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("Раздел:"):
            current_section = line[7:].strip()
        elif line.startswith("Тема:") and current_section:
            topic = line[5:].strip()
            if topic:
                result.append((current_section, topic))
    return result


def get_plan() -> str:
    plan_text = read_project_file("content-plan.md")
    used = get_used_topics()
    wp_titles = wp_posts.get_post_titles()

    def _is_used(topic: str) -> bool:
        if topic.lower() in used:
            return True
        topic_words = set(re.sub(r"[^\w\s]", " ", topic.lower()).split())
        for title in wp_titles:
            title_words = set(re.sub(r"[^\w\s]", " ", title.lower()).split())
            if len(topic_words & title_words) >= 3:
                return True
        return False

    lines = []
    total = done = 0
    for line in plan_text.splitlines():
        if re.match(r"^\d+\.\s+", line):
            topic = re.sub(r"^\d+\.\s+", "", line).strip()
            total += 1
            if _is_used(topic):
                done += 1
                lines.append(f"✅ {line}")
            else:
                lines.append(f"⬜ {line}")
        else:
            lines.append(line)

    result = "\n".join(lines)
    if total > 0:
        result += f"\n\n📊 Написано: {done}/{total} тем ({total - done} осталось)"
    return result
