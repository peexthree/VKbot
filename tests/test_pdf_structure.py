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

    spread = TAROT_SPREADS["tarot_misses"]
    positions = spread["positions"]
    card_ids = ["28", "4", "42", "22", "39"]

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

    sample_user_text = """Добро пожаловать в пространство, где тишина обретает голос, а скрытое становится явным. Мы открываем Сакральная ясность для того, кто ищет истину сквозь завесу разлуки.

1 СКУЧАЕТ ЛИ ОН - СЕМЕРКА ЖЕЗЛОВ.
Этот человек ведет невидимую внутреннюю борьбу, защищая свое пространство от нахлынувших воспоминаний. Он держит оборону против собственных чувств, но сама необходимость защищаться доказывает - образ живет в его сердце.

🌙 Позиция 2. Что мешает быть вместе - Император.
Между вами стоит непреклонная стена из гордости, принципов и жесткого контроля. Кто-то из вас привык подчинять эмоции разуму, воздвигнув ледяной трон из невысказанных амбиций.

🕯 Позиция 3. Что он чувствует - Семерка Кубков.
Его душа окутана туманом иллюзий, сомнений и сладких миражей. Он тонет в фантазиях о том, как всё могло быть иначе, но боится сделать шаг из мира грёз в суровую реальность.

✨ Позиция 4. Будем ли мы вместе - Двойка Жезлов.
Судьба замерла на перекрестке дорог в ожидании решительного импульса. Калибровка путей показывает состояние неопределенности, когда оба смотрят вдаль, но стоят на пороге выбора.

5 СОВЕТ ОТ КАРТ - ЧЕТВЕРКА КУБКОВ.
Оракул шепчет о необходимости прекратить бездумно смотреть в пустые чаши прошлого. Обрати свой взор внутрь себя - Резонанс истины кроется в обретении внутренней целостности независимо от внешних обстоятельств.

🌟 СИНТЕЗ КАРТ И САКРАЛЬНЫЙ СОВЕТ
Главный урок этого союза заключается в прохождении через испытание гордостью и иллюзиями. Предостережение звучит просто - не трать жизненную силу на ожидание того, кто сам боится собственной тени. Вектор исхода зависит от твоей способности выйти из режима обороны и обрести самодостаточность. Когда ты перестанешь цепляться за призраки, пространство само переплетет ваши нити заново."""

    parsed = parse_tarot_reading(sample_user_text, positions)
    assert "Добро пожаловать" in parsed["prologue"]
    assert len(parsed["sections"]) == 5, f"Expected 5 sections, got {len(parsed['sections'])}"
    assert "Главный урок этого союза" in parsed["synthesis"]

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

    # Ensure cover path resolves properly without double uslugi
    raw_img = spread["image_name"].replace("\\", "/").strip()
    if raw_img.startswith("cards/"):
        spread_cover = raw_img
    elif raw_img.startswith("uslugi/"):
        spread_cover = f"cards/{raw_img}"
    else:
        spread_cover = f"cards/uslugi/{raw_img}"

    assert spread_cover == "cards/uslugi/tarot_misses.jpg"
    assert os.path.exists(spread_cover), f"Cover image {spread_cover} does not exist!"

    tmpl = jinja2.Template(TAROT_SPREAD_TEMPLATE)
    html_out = tmpl.render(
        user_name="Игорь",
        birth_info="15.6.1991 12:00 Казань",
        spread_title="СКУЧАЕТ ЛИ ОН ПО МНЕ",
        spread_cover=spread_cover,
        character_name="Честный Оракул",
        current_date="09.11.2026",
        cards_list=cards_list,
        prologue=parsed["prologue"],
        sections=sections,
        synthesis=parsed["synthesis"],
        formatted_full_text=sample_user_text
    )

    assert "СВЯЩЕННАЯ КАРТА РАСКЛАДА" in html_out
    assert "cards/uslugi/tarot_misses.jpg" in html_out
    assert "Семерка Жезлов" in html_out
    assert "СИНТЕЗ КАРТ И САКРАЛЬНЫЙ СОВЕТ" in html_out
    # Check no emoji remains in rendered text
    assert "🌟" not in html_out
    assert "🌙" not in html_out
    assert "🕯" not in html_out
    assert "✨" not in html_out
    print("test_spread_rendering passed!")

def test_classic_group_e_fallback():
    from prompts.pdf_templates import GROUP_E_TEMPLATE
    tmpl = jinja2.Template(GROUP_E_TEMPLATE)

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
    assert "<h3>2. Кармический Урок Ситуации</h3>" not in html_out
    print("test_classic_group_e_fallback passed!")

if __name__ == "__main__":
    test_template_syntax()
    test_spread_rendering()
    test_classic_group_e_fallback()
    print("ALL TESTS PASSED SUCCESSFULLY!")
