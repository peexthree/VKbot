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
    eye_photo: str = None
):
    try:
        template = jinja_env.get_template('report.html')

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
            eye_photo=eye_photo
        )

        from weasyprint import HTML
        HTML(string=html_out, base_url=project_root).write_pdf(output_filename)

        logger.success(f"PDF успешно создан: {output_filename}")
        return True
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        return False
