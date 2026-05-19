import os
from loguru import logger
from modules.utils.consts import jinja_env

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
    natal_chart_path: str = None
):
    try:
        template = jinja_env.get_template('report.html')

        def safe_br(val):
            if val is None:
                return ""
            if isinstance(val, list):
                val = "\n".join([str(i) for i in val])
            return str(val).replace('\n', '<br>')

        formatted_text = safe_br(text_content)
        formatted_advice = safe_br(advice_content)
        shadow_side = safe_br(shadow_side)
        activation_comment = safe_br(activation_comment)
        affirmations = safe_br(affirmations)
        thirty_day_forecast = safe_br(thirty_day_forecast)
        activation_recommendations = safe_br(activation_recommendations)
        star_code = safe_br(star_code)
        energy_map = safe_br(energy_map)

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
            natal_chart_path=natal_chart_path
        )

        from weasyprint import HTML
        # Explicitly pass base_url for resolving relative paths to images
        HTML(string=html_out, base_url=project_root).write_pdf(output_filename)

        logger.success(f"PDF успешно создан: {output_filename}")
        return True
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        return False
