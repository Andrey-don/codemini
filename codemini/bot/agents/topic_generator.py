from bot.utils.openrouter import call_agent

MODEL = "anthropic/claude-haiku-4-5"
TEMPERATURE = 0.9

SYSTEM_PROMPT = """Ты — контент-стратег для партнёрского сайта об онлайн-школах программирования для детей codemini.ru.

Генерируешь новые темы статей, которые:
- Отвечают на реальные вопросы родителей
- Имеют поисковый спрос (что ищут в Яндексе)
- Не дублируют уже написанные темы
- Подходят под рубрики сайта: Обзоры школ, По возрасту, По направлениям, Сравнения, Блог

Формат ответа — СТРОГО так (по одной теме на строку):
Раздел: Название раздела
Тема: Тема статьи
Раздел: Название раздела
Тема: Тема статьи
..."""


def run(used_topics: list[str], sections: list[str], topics_per_section: int = 10) -> str:
    used_str = "\n".join(f"- {t}" for t in used_topics[:50])
    sections_str = "\n".join(f"- {s}" for s in sections)
    context = f"""
РАЗДЕЛЫ САЙТА:
{sections_str}

УЖЕ НАПИСАННЫЕ ТЕМЫ (не повторять):
{used_str}

Сгенерируй {topics_per_section} новых тем для каждого раздела.
Темы должны быть конкретными и отвечать на вопросы родителей о курсах программирования для детей.
"""
    return call_agent(SYSTEM_PROMPT, context, MODEL, TEMPERATURE)
