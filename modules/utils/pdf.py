import os
import re
from loguru import logger

def clean_slang(text: str) -> str:
    if not text:
        return ""

    replacements = [
        # ПЕРЕПРОШИВКА УСПЕХА -> АКТИВАЦИЯ ИЗОБИЛИЯ
        (r'ПЕРЕПРОШИВКА\s+УСПЕХА', 'АКТИВАЦИЯ ИЗОБИЛИЯ'),
        (r'перепрошивка\s+успеха', 'активация изобилия'),
        (r'Перепрошивка\s+успеха', 'Активация изобилия'),
        (r'Перепрошивка\s+Успеха', 'Активация Изобилия'),

        # перепрошивка
        (r'\bПЕРЕПРОШИВКА\b', 'ТРАНСФОРМАЦИЯ'),
        (r'\bперепрошивка\b', 'трансформация'),
        (r'\bПерепрошивка\b', 'Трансформация'),
        (r'\bПЕРЕПРОШИВКИ\b', 'ТРАНСФОРМАЦИИ'),
        (r'\bперепрошивки\b', 'трансформации'),
        (r'\bПерепрошивки\b', 'Трансформации'),
        (r'\bПЕРЕПРОШИВКУ\b', 'ТРАНСФОРМАЦИЮ'),
        (r'\bперепрошивку\b', 'трансформацию'),
        (r'\bПерепрошивку\b', 'Трансформирование'),

        # прошивка
        (r'\bПРОШИВКА\b', 'СУДЬБА'),
        (r'\bпрошивка\b', 'судьба'),
        (r'\bПрошивка\b', 'Судьба'),
        (r'\bПРОШИВКИ\b', 'СУДЬБЫ'),
        (r'\bпрошивки\b', 'судьбы'),
        (r'\bПрошивки\b', 'Судьбы'),
        (r'\bПРОШИВКУ\b', 'СУДЬБУ'),
        (r'\bпрошивку\b', 'судьбу'),
        (r'\bПрошивку\b', 'Судьбу'),
        (r'\bПРОШИВКОЙ\b', 'СУДЬБОЙ'),
        (r'\bпрошивкой\b', 'судьбой'),
        (r'\bПрошивкой\b', 'Судьбой'),

        # перепрошить
        (r'\bПЕРЕПРОШИТЬ\b', 'ТРАНСФОРМИРОВАТЬ'),
        (r'\bперепрошить\b', 'трансформировать'),
        (r'\bПерепрошить\b', 'Трансформировать'),

        # баг
        (r'\bБАГ\b', 'УРОК'),
        (r'\bбаг\b', 'урок'),
        (r'\bБаг\b', 'Урок'),
        (r'\bБАГИ\b', 'УРОКИ'),
        (r'\bбаги\b', 'уроки'),
        (r'\bБаги\b', 'Уроки'),
        (r'\bБАГОВ\b', 'УРОКОВ'),
        (r'\bбагов\b', 'уроков'),
        (r'\bБагов\b', 'Уроков'),

        # код
        (r'\bКОД\b', 'ПОТОК'),
        (r'\bкод\b', 'поток'),
        (r'\bКод\b', 'Поток'),
        (r'\bКОДА\b', 'ПОТОКА'),
        (r'\bкода\b', 'потока'),
        (r'\bКода\b', 'Потока'),
        (r'\bКОДУ\b', 'ПОТОКУ'),
        (r'\bкоду\b', 'потоку'),
        (r'\bКоду\b', 'Потоку'),
        (r'\bКОДОМ\b', 'ПОТОКОМ'),
        (r'\bкодом\b', 'потоком'),
        (r'\bКодом\b', 'Потоком'),
        (r'\bКОДЕ\b', 'ПОТОКЕ'),
        (r'\bкоде\b', 'потоке'),
        (r'\bКоде\b', 'Потоке'),
        (r'\bКОДЫ\b', 'ПОТОКИ'),
        (r'\bкоды\b', 'потоки'),
        (r'\bКоды\b', 'Потоки'),
        (r'\bКОДОВ\b', 'ПОТОКОВ'),
        (r'\bкодов\b', 'потоков'),
        (r'\bКодов\b', 'Потоков'),

        # матрица
        (r'\bМАТРИЦА\b', 'КОСМОС'),
        (r'\bматрица\b', 'космос'),
        (r'\bМатрица\b', 'Космос'),
        (r'\bМАТРИЦЫ\b', 'КОСМОСА'),
        (r'\bматрицы\b', 'космоса'),
        (r'\bМатрицы\b', 'Космоса'),
        (r'\bМАТРИЦУ\b', 'КОСМОС'),
        (r'\bматрицу\b', 'космос'),
        (r'\bМатрицу\b', 'Космос'),
        (r'\bМАТРИЦЕЙ\b', 'КОСМОСОМ'),
        (r'\bматрицей\b', 'космосом'),
        (r'\bМатрицей\b', 'Космосом'),
        (r'\bМАТРИЦЕ\b', 'КОСМОСЕ'),
        (r'\bматрице\b', 'космосе'),
        (r'\bМатрице\b', 'Космосе'),

        # взлом
        (r'\bВЗЛОМ\b', 'РАСКРЫТИЕ'),
        (r'\bвзлом\b', 'раскрытие'),
        (r'\bВзлом\b', 'Раскрытие'),
        (r'\bВЗЛОМА\b', 'РАСКРЫТИЯ'),
        (r'\bвзлома\b', 'раскрытия'),
        (r'\bВзлома\b', 'Раскрытия'),
        (r'\bВЗЛОМУ\b', 'РАСКРЫТИЮ'),
        (r'\bвзлому\b', 'раскрытию'),
        (r'\bВзлому\b', 'Раскрытию'),
        (r'\bВЗЛОМОМ\b', 'РАСКРЫТИЕМ'),
        (r'\bвзломом\b', 'раскрытием'),
        (r'\bВзломом\b', 'Раскрытием'),
        (r'\bВЗЛОМЕ\b', 'РАСКРЫТИИ'),
        (r'\bвзломе\b', 'раскрытии'),
        (r'\bВзломе\b', 'Раскрытии'),
        (r'\bВЗЛОМАТЬ\b', 'РАСКРЫТЬ'),
        (r'\bвзломать\b', 'раскрыть'),
        (r'\bВзломать\b', 'Раскрыть'),
        (r'\bВЗЛОМАН\b', 'РАСКРЫТ'),
        (r'\bвзломан\b', 'раскрыт'),
        (r'\bВзломан\b', 'Раскрыт'),
        (r'\bВЗЛОМАНА\b', 'РАСКРЫТА'),
        (r'\bвзломана\b', 'раскрыта'),
        (r'\bВзломана\b', 'Раскрыта'),
        (r'\bВЗЛОМАНО\b', 'РАСКРЫТО'),
        (r'\bвзломано\b', 'раскрыто'),
        (r'\bВзломано\b', 'Раскрыто'),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    from ai.logic import sanitize_premium_tov
    text = sanitize_premium_tov(text)
    text = strip_emojis(text)

    return text

def strip_emojis(text: str) -> str:
    """Удаляет символы Unicode Emoji для предотвращения 'квадратиков' (□) в шрифтах WeasyPrint."""
    if not text:
        return ""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
        "\U00002600-\U000026FF"  # misc symbols
        "\U00002300-\U000023FF"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)

def parse_tarot_reading(text: str, spread_positions: list = None) -> dict:
    """Интеллектуальный парсер текста расклада Таро на пролог, позиции и синтез."""
    if not text:
        return {"prologue": "", "sections": [], "synthesis": ""}

    cleaned = strip_emojis(text.replace("\r\n", "\n").replace("\r", "\n")).strip()

    # Поиск номерованных позиций (1., 1), **1., ### 1., Позиция 1:, 🌙 Позиция 2., 1 СКУЧАЕТ ЛИ ОН и т.д.)
    pos_regex = re.compile(
        r"(?m)^[^\w\n\r]*?(?:(?:Позиция|Карта|Аркан)\s*)?(\d+)[\.\)\:\s]\s*([^\n\r]+)$",
        re.UNICODE | re.IGNORECASE,
    )

    matches = list(pos_regex.finditer(cleaned))
    prologue = ""
    sections = []
    synthesis_text = ""

    if matches:
        prologue = cleaned[: matches[0].start()].strip()
        prologue = re.sub(r"^[*#_~✦\s]+", "", prologue).strip()

        # Поиск синтеза/совета после последней позиции
        last_match = matches[-1]
        last_pos_text = cleaned[last_match.start() :]

        syn_regex = re.compile(
            r"(?im)^[^\w\d\n\r]*?(?:СИНТЕЗ(?:\s+КАРТ)?|САКРАЛЬНЫЙ\s+СОВЕТ|ИТОГ|НАПУТСТВИЕ|РЕЗЮМЕ|ЗАКЛЮЧЕНИЕ)[\s\w]*?[:—–\-]?\s*?\n+(.+)$",
            re.DOTALL | re.UNICODE,
        )
        syn_match = syn_regex.search(last_pos_text)
        main_limit = len(cleaned)
        if syn_match:
            synthesis_text = syn_match.group(1).strip()
            main_limit = last_match.start() + syn_match.start()

        for i, m in enumerate(matches):
            num = int(m.group(1))
            raw_title = m.group(2).strip()
            title = re.sub(r"[*#_~`]", "", raw_title).strip()
            title = re.sub(r"[:—–\-]+$", "", title).strip()

            start_idx = m.end()
            if i + 1 < len(matches):
                end_idx = matches[i + 1].start()
            else:
                end_idx = main_limit

            body = cleaned[start_idx:end_idx].strip()
            body = re.sub(r"^[*#_~`\s]+", "", body).strip()

            sections.append({
                "num": num,
                "title": title,
                "content": body,
            })
    else:
        # Резервный режим: разделение по абзацам
        paras = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        if len(paras) > 1:
            prologue = paras[0]
            for idx, p in enumerate(paras[1:], 1):
                pos_title = (
                    spread_positions[idx - 1]
                    if spread_positions and idx - 1 < len(spread_positions)
                    else f"Откровение {idx}"
                )
                sections.append({
                    "num": idx,
                    "title": pos_title,
                    "content": p,
                })
        else:
            sections.append({
                "num": 1,
                "title": "Сакральное Толкование",
                "content": cleaned,
            })

    return {
        "prologue": prologue,
        "sections": sections,
        "synthesis": synthesis_text,
    }

def generate_premium_pdf(
    user_name: str,
    birth_info: str,
    section_name: str,
    text_content: str,
    output_filename: str,
    card_id: str = None,
    advice_content: str = "",
    card_name: str = None,
    card_description: str = None,
    shadow_side: str = "",
    activation_level: int = 100,
    activation_comment: str = "",
    affirmations: str = "",
    next_activation_date: str = "",
    thirty_day_forecast: str = "",
    activation_recommendations: str = "",
    star_code: str = "",
    energy_map: str = "",
    current_date: str = "",
    palm_photos: list[str] = None,
    interesting_facts: str = "",
    character_name: str = "Проводник",
    sigil_photo: str = None,
    eye_photo: str = None,
    **kwargs
):
    try:
        from prompts.pdf_templates import get_html_template, TAROT_SPREAD_TEMPLATE
        from configs.tarot_spreads import TAROT_SPREADS, TAROT_SPREAD_KEYS
        from jinja2 import Template

        raw_section = (
            kwargs.get("section_key")
            or kwargs.get("raw_section")
            or kwargs.get("section")
            or section_name
            or ""
        )
        if isinstance(raw_section, str):
            raw_section = raw_section.lower().strip()
        else:
            raw_section = str(raw_section)

        def safe_br(val):
            if val is None:
                return ""
            if isinstance(val, list):
                val = "\n".join([str(i) for i in val])
            cleaned_val = clean_slang(str(val))
            return cleaned_val.replace('\n', '<br>')

        formatted_text = safe_br(text_content)
        formatted_advice = safe_br(advice_content)
        shadow_side = safe_br(shadow_side)
        activation_comment = safe_br(activation_comment)
        affirmations = safe_br(affirmations)
        thirty_day_forecast = safe_br(thirty_day_forecast)
        activation_recommendations = safe_br(activation_recommendations)
        interesting_facts = safe_br(interesting_facts)
        star_code = safe_br(star_code)
        energy_map = safe_br(energy_map)

        user_name = clean_slang(user_name)
        birth_info = clean_slang(birth_info)
        section_name = clean_slang(section_name)
        card_name = clean_slang(card_name) if card_name else ""
        card_description = clean_slang(card_description) if card_description else ""

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # Определяем, является ли данный заказ сакральным раскладом Таро
        cards_kw = kwargs.get("cards")
        is_tarot_spread = (
            raw_section in TAROT_SPREADS
            or raw_section in TAROT_SPREAD_KEYS
            or raw_section.startswith("tarot_")
            or any(k in raw_section for k in TAROT_SPREAD_KEYS)
            or (isinstance(cards_kw, list) and len(cards_kw) > 1)
        )

        if is_tarot_spread:
            # Находим метаданные расклада
            spread = TAROT_SPREADS.get(raw_section)
            if not spread:
                for k, sp in TAROT_SPREADS.items():
                    if k in raw_section or sp["title"].lower() in raw_section:
                        spread = sp
                        break

            raw_title = kwargs.get("title") or (spread["title"] if spread else section_name)
            spread_title = clean_slang(raw_title).strip()
            spread_title = re.sub(r"^[\"«\s]+|[\"»\s]+$", "", spread_title)

            # Корректное разрешение пути к обложке без дублирования префиксов
            if spread and spread.get("image_name"):
                raw_img = spread["image_name"].replace("\\", "/").strip()
                if raw_img.startswith("cards/"):
                    spread_cover = raw_img
                elif raw_img.startswith("uslugi/"):
                    spread_cover = f"cards/{raw_img}"
                else:
                    spread_cover = f"cards/uslugi/{raw_img}"
            else:
                spread_cover = "cards/uslugi/tarot_cat.jpg"

            cards_raw = cards_kw or ([card_id] if card_id else [])
            positions = spread.get("positions", []) if spread else []
            from cards_data import get_card_data

            cards_list = []
            for idx, cid in enumerate(cards_raw):
                c_str = str(cid)
                c_data = get_card_data(c_str)
                pos_title = positions[idx] if idx < len(positions) else f"Позиция {idx + 1}"
                c_name = c_data.get("name") or f"Аркан {c_str}"
                c_img = f"cards/{c_str}.jpeg"
                cards_list.append({
                    "num": idx + 1,
                    "cid": c_str,
                    "name": clean_slang(c_name),
                    "subtitle": clean_slang(c_data.get("subtitle", "")),
                    "pos_title": clean_slang(pos_title),
                    "img_path": c_img
                })

            parsed = parse_tarot_reading(text_content, positions)
            prologue = safe_br(parsed.get("prologue", ""))
            synthesis = safe_br(parsed.get("synthesis", ""))

            sections = []
            for s in parsed.get("sections", []):
                s_num = s.get("num", 1)
                card_name_match = ""
                pos_fallback = ""
                if 1 <= s_num <= len(cards_list):
                    card_name_match = cards_list[s_num - 1]["name"]
                    pos_fallback = cards_list[s_num - 1].get("pos_title", "")

                raw_t = s.get("title", "")
                clean_t = raw_t
                if card_name_match:
                    patt = re.compile(
                        r"[:—–\-\s(]+(" + re.escape(card_name_match) + r")[)\s.]*$",
                        re.IGNORECASE,
                    )
                    clean_t = patt.sub("", clean_t).strip()
                clean_t = re.sub(r"[:—–\-.\s]+$", "", clean_t).strip()
                if not clean_t and pos_fallback:
                    clean_t = pos_fallback

                sections.append({
                    "num": s_num,
                    "title": clean_slang(clean_t),
                    "card_name": card_name_match,
                    "content": safe_br(s.get("content", ""))
                })

            template = Template(TAROT_SPREAD_TEMPLATE)
            html_out = template.render(
                user_name=user_name,
                birth_info=birth_info,
                spread_title=spread_title,
                spread_cover=spread_cover,
                character_name=character_name,
                current_date=current_date,
                cards_list=cards_list,
                prologue=prologue,
                sections=sections,
                synthesis=synthesis,
                formatted_full_text=formatted_text,
            )
        else:
            # Стандартные сервисы групп A, B, C, D, E
            template_str = get_html_template(raw_section)
            template = Template(template_str)

            # Format group-specific keys to be passed to templates
            geom_analysis = safe_br(kwargs.get("geom_analysis", ""))
            activation_ritual = safe_br(kwargs.get("activation_ritual", ""))
            energy_vector = safe_br(kwargs.get("energy_vector", ""))

            fm_val = kwargs.get("focus_mantras", "")
            if isinstance(fm_val, list):
                focus_mantras = "".join([f"<li>{clean_slang(str(m))}</li>" for m in fm_val])
            else:
                focus_mantras = safe_br(fm_val)

            iris_or_line_decoding = safe_br(kwargs.get("iris_or_line_decoding", ""))
            spiritual_vulnerability = safe_br(kwargs.get("spiritual_vulnerability", ""))
            intuition_unlk = safe_br(kwargs.get("intuition_unlk", ""))
            daily_mudras = safe_br(kwargs.get("daily_mudras", ""))

            message_from_abyss = safe_br(kwargs.get("message_from_abyss", ""))
            shadow_integration = safe_br(kwargs.get("shadow_integration", ""))
            sacred_taboo = safe_br(kwargs.get("sacred_taboo", ""))
            astral_totem_ritual = safe_br(kwargs.get("astral_totem_ritual", ""))

            macrocosm_resonance = safe_br(kwargs.get("macrocosm_resonance", ""))
            balance_formula = safe_br(kwargs.get("balance_formula", ""))
            space_alignment = safe_br(kwargs.get("space_alignment", ""))
            cosmic_frequency_status = clean_slang(str(kwargs.get("cosmic_frequency_status", "")))

            tarot_arcana_analysis = safe_br(kwargs.get("tarot_arcana_analysis", ""))
            karmic_lesson = safe_br(kwargs.get("karmic_lesson", ""))
            energy_alignment_tips = safe_br(kwargs.get("energy_alignment_tips", ""))

            da_val = kwargs.get("daily_affirmations", "")
            if isinstance(da_val, list):
                daily_affirmations = "".join([f"<li>{clean_slang(str(a))}</li>" for a in da_val])
            else:
                daily_affirmations = safe_br(da_val)

            # Гарантия от пустых блоков: если структурированные поля отсутствуют, используем полный текст
            if not tarot_arcana_analysis and formatted_text:
                tarot_arcana_analysis = formatted_text
            if not geom_analysis and formatted_text:
                geom_analysis = formatted_text
            if not iris_or_line_decoding and formatted_text:
                iris_or_line_decoding = formatted_text
            if not message_from_abyss and formatted_text:
                message_from_abyss = formatted_text
            if not macrocosm_resonance and formatted_text:
                macrocosm_resonance = formatted_text

            card_image_path = f"cards/{card_id}.jpeg" if card_id else ""

            html_out = template.render(
                user_name=user_name,
                birth_info=birth_info,
                section_name=section_name,
                text_content=formatted_text,
                advice_content=formatted_advice,
                card_name=card_name or "",
                card_description=card_description or "",
                card_image_path=card_image_path,
                shadow_side=shadow_side,
                activation_level=activation_level,
                activation_comment=activation_comment,
                affirmations=affirmations,
                next_activation_date=next_activation_date,
                thirty_day_forecast=thirty_day_forecast,
                activation_recommendations=activation_recommendations,
                star_code=star_code,
                energy_map=energy_map,
                current_date=current_date,
                palm_photos=palm_photos,
                interesting_facts=interesting_facts,
                character_name=character_name,
                sigil_photo=sigil_photo,
                eye_photo=eye_photo,

                # Group specific fields
                geom_analysis=geom_analysis,
                activation_ritual=activation_ritual,
                energy_vector=energy_vector,
                focus_mantras=focus_mantras,

                iris_or_line_decoding=iris_or_line_decoding,
                spiritual_vulnerability=spiritual_vulnerability,
                intuition_unlk=intuition_unlk,
                daily_mudras=daily_mudras,

                message_from_abyss=message_from_abyss,
                shadow_integration=shadow_integration,
                sacred_taboo=sacred_taboo,
                astral_totem_ritual=astral_totem_ritual,

                macrocosm_resonance=macrocosm_resonance,
                balance_formula=balance_formula,
                space_alignment=space_alignment,
                cosmic_frequency_status=cosmic_frequency_status,

                tarot_arcana_analysis=tarot_arcana_analysis,
                karmic_lesson=karmic_lesson,
                energy_alignment_tips=energy_alignment_tips,
                daily_affirmations=daily_affirmations
            )

        from weasyprint import HTML
        HTML(string=html_out, base_url=project_root).write_pdf(output_filename)

        logger.success(f"PDF успешно создан: {output_filename}")
        return True
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        return False
