import os
import sys
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jinja2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_template_syntax():
    from prompts.pdf_templates import (
        GROUP_A_TEMPLATE,
        GROUP_B_TEMPLATE,
        GROUP_C_TEMPLATE,
        GROUP_D_TEMPLATE,
        GROUP_E_TEMPLATE,
        TAROT_SPREAD_TEMPLATE,
        get_html_template,
    )
    for name, tmpl_str in [
        ("GROUP_A", GROUP_A_TEMPLATE),
        ("GROUP_B", GROUP_B_TEMPLATE),
        ("GROUP_C", GROUP_C_TEMPLATE),
        ("GROUP_D", GROUP_D_TEMPLATE),
        ("GROUP_E", GROUP_E_TEMPLATE),
        ("TAROT_SPREAD", TAROT_SPREAD_TEMPLATE),
    ]:
        try:
            jinja2.Template(tmpl_str)
            print(f"Template {name} OK")
        except Exception as e:
            print(f"Error in {name}: {e}")
            raise e

def test_spread_rendering():
    # Load pdf.py directly using SourceFileLoader to avoid uninstalled dependencies in test env
    # Mock loguru module if not present
    import types
    if "loguru" not in sys.modules:
        m = types.ModuleType("loguru")
        m.logger = types.SimpleNamespace(
            info=lambda *a, **k: None,
            success=lambda *a, **k: None,
            error=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            debug=lambda *a, **k: None
        )
        sys.modules["loguru"] = m

    pdf_path = os.path.join(os.path.dirname(__file__), "..", "modules", "utils", "pdf.py")
    spec = importlib.util.spec_from_file_location("pdf_module", pdf_path)
    pdf_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pdf_module)

    parse_tarot_reading = pdf_module.parse_tarot_reading

    from configs.tarot_spreads import TAROT_SPREADS
    from prompts.pdf_templates import TAROT_SPREAD_TEMPLATE
    from cards_data import get_card_data

    spread = TAROT_SPREADS["tarot_pause_end"]
    positions = spread["positions"]
    card_ids = ["12", "0", "15"]

    cards_list = []
    for idx, cid in enumerate(card_ids):
        c_data = get_card_data(cid)
        cards_list.append({
            "num": idx + 1,
            "cid": cid,
            "name": c_data.get("name", f"Аркан {cid}"),
            "subtitle": c_data.get("subtitle", ""),
            "pos_title": positions[idx],
            "img_path": f"cards/{cid}.jpeg"
        })

    text = """В ночной тишине карты открывают истину. Тени прошлого отступают.

🔮 1. Что сейчас: пауза или завершение?
Сейчас связь находится в подвешенном состоянии. Не торопите события.

🔮 2. Есть ли у этой связи продолжение?
Карты говорят, что шанс на новый виток отношений высок.

🔮 3. Что мешает возобновлению?
Внутренние сомнения и страх снова обжечься.

Совет от карт:
Отпустите обиды и откройте сердце диалогу."""

    parsed = parse_tarot_reading(text, positions)
    assert parsed["prologue"] == "В ночной тишине карты открывают истину. Тени прошлого отступают."
    assert len(parsed["sections"]) == 3
    assert "Отпустите обиды" in parsed["synthesis"]

    sections = []
    for s in parsed["sections"]:
        s_num = s["num"]
        card_name = cards_list[s_num - 1]["name"] if s_num <= len(cards_list) else ""
        sections.append({
            "num": s_num,
            "title": s["title"],
            "card_name": card_name,
            "content": s["content"]
        })

    tmpl = jinja2.Template(TAROT_SPREAD_TEMPLATE)
    html_out = tmpl.render(
        user_name="Адепт",
        birth_info="12.04.1995 14:00 Москва",
        spread_title=spread["title"],
        spread_cover=f"cards/uslugi/{spread['image_name']}",
        character_name="Олеся",
        current_date="09.11.2026",
        cards_list=cards_list,
        prologue=parsed["prologue"],
        sections=sections,
        synthesis=parsed["synthesis"],
        formatted_full_text=text
    )

    assert "СВЯЩЕННАЯ КАРТА РАСКЛАДА" in html_out
    assert "Что сейчас: пауза или завершение?" in html_out
    assert "Повешенный" in html_out
    assert "СИНТЕЗ КАРТ И САКРАЛЬНЫЙ СОВЕТ" in html_out
    assert "Отпустите обиды" in html_out
    print("test_spread_rendering passed!")

def test_classic_group_e_fallback():
    from prompts.pdf_templates import GROUP_E_TEMPLATE
    tmpl = jinja2.Template(GROUP_E_TEMPLATE)

    # When tarot_arcana_analysis is absent, formatted text is used
    html_out = tmpl.render(
        user_name="Иван",
        birth_info="01.01.2000",
        section_name="АНТИТАРО",
        text_content="Полный текст антитаро без пустых блоков.",
        tarot_arcana_analysis="",
        karmic_lesson="",
        energy_alignment_tips="",
        daily_affirmations=""
    )

    assert "Сакральное Толкование" in html_out
    assert "Полный текст антитаро без пустых блоков." in html_out
    # Ensure empty panels for karmic lesson etc are omitted
    assert "<h3>2. Кармический Урок Ситуации</h3>" not in html_out
    print("test_classic_group_e_fallback passed!")

if __name__ == "__main__":
    test_template_syntax()
    test_spread_rendering()
    test_classic_group_e_fallback()
    print("ALL TESTS PASSED SUCCESSFULLY!")
