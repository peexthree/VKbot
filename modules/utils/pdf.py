import os
import re
from loguru import logger
from modules.utils.consts import jinja_env

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
        (r'\bПерепрошивку\b', 'Трансформацию'),
        (r'\bПЕРЕПРОШИВКОЙ\b', 'ТРАНСФОРМАЦИЕЙ'),
        (r'\bперепрошивкой\b', 'трансформацией'),
        (r'\bПерепрошивкой\b', 'Трансформацией'),

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

    return text

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
        from prompts.pdf_templates import get_html_template
        from jinja2 import Template

        section_key = section_name.lower()
        template_str = get_html_template(section_key)
        template = Template(template_str)

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

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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
