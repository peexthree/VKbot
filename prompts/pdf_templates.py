# -*- coding: utf-8 -*-

# Кастомные HTML-шаблоны WeasyPrint для каждой из 5 групп услуг

GROUP_A_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 0;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: linear-gradient(rgba(15, 11, 20, 0.85), rgba(15, 11, 20, 0.85)), url('cards/uslugi/pdf_background_final.png') no-repeat center center; /* Тинт угля + общий мистический фон */
            background-size: cover;
            color: #f7e9cc;
        }
        .container {
            min-height: 100vh;
            position: relative;
            box-sizing: border-box;
        }
        .cover {
            height: 280mm;
            position: relative;
            padding-top: 40px;
            text-align: center;
        }
        .logo-top {
            display: block;
            width: 25%;
            margin: 0 auto 20px auto;
        }
        .sigil-header-img {
            display: block;
            max-width: 130mm;
            max-height: 130mm;
            margin: 30px auto;
            border-radius: 50%;
            border: 4px solid #d4af37;
            box-shadow: 0 0 35px rgba(212, 175, 55, 0.7);
        }
        .user-info-wrapper {
            position: absolute;
            bottom: 40mm;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 10, 20, 0.9);
            padding: 20px 60px;
            border-radius: 12px;
            border: 2px solid #d4af37;
            box-shadow: 0 0 30px rgba(212, 175, 55, 0.4);
            min-width: 440px;
        }
        .user-info {
            font-size: 13pt;
            font-weight: 700;
            color: #ffe8a3;
            line-height: 1.6;
        }
        .highlight { color: #ffffff; }

        .content-wrapper {
            background: rgba(25, 20, 35, 0.85);
            border: 1px solid rgba(212, 175, 55, 0.3);
            border-radius: 16px;
            padding: 40px 45px;
            margin: 40px 50px;
        }
        .content-title {
            font-size: 20pt;
            font-weight: 700;
            color: #d4af37;
            text-align: center;
            margin-bottom: 30px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .panel {
            background: rgba(35, 28, 48, 0.7);
            border-left: 4px solid #d4af37;
            border-radius: 8px;
            padding: 22px 26px;
            margin: 30px 0;
        }
        .panel h3 {
            font-size: 14pt;
            font-weight: 700;
            color: #ffe8a3;
            margin-top: 0;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .panel p {
            font-size: 12pt;
            line-height: 1.65;
            margin: 0;
            text-align: justify;
        }
        .mantras-list {
            margin: 15px 0 0 0;
            padding-left: 20px;
        }
        .mantras-list li {
            font-style: italic;
            font-size: 12.5pt;
            color: #ffe8a3;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container cover">
        <img src="cards/uslugi/logo.png" class="logo-top" alt="Logo">
        {% if sigil_photo %}
        <img src="{{ sigil_photo }}" class="sigil-header-img" alt="Сигил">
        {% else %}
        <img src="cards/uslugi/head2.png" class="sigil-header-img" style="border-radius: 12px;" alt="Печать">
        {% endif %}
        <div class="user-info-wrapper">
            <div class="user-info">
                РИТУАЛ: <span class="highlight">{{ section_name }}</span><br>
                ИМЯ: <span class="highlight">{{ user_name }}</span><br>
                ТОЧКА ВХОДА: {{ birth_info }}
            </div>
        </div>
    </div>
    <div style="page-break-before: always;"></div>

    <div class="container">
        <div class="content-wrapper">
            <div class="content-title">Печать Изобилия и Удачи</div>

            <div class="panel">
                <h3>1. Сакральная Геометрия Знака</h3>
                <p>{{ geom_analysis | safe }}</p>
            </div>

            <div class="panel">
                <h3>2. Ритуал Ментальной Активации</h3>
                <p>{{ activation_ritual | safe }}</p>
            </div>

            <div class="panel">
                <h3>3. Энергетический Вектор Действия</h3>
                <p>{{ energy_vector | safe }}</p>
            </div>

            <div class="panel">
                <h3>4. Мантры Фиксации Сознания</h3>
                <ul class="mantras-list">
                    {{ focus_mantras | safe }}
                </ul>
            </div>
        </div>
    </div>

    <div style="page-break-before: always;"></div>
    <div class="container" style="text-align: center; padding-top: 60mm; height: 280mm;">
        <div style="margin-bottom: 40px;">
            <img src="cards/uslugi/logo.png" style="width: 200px; display: block; margin: 0 auto;">
        </div>
        <div style="color: #ffe8a3;">
            <p style="font-weight: 700; font-size: 18pt; letter-spacing: 2px;">РИТУАЛ СИГИЛА ЗАВЕРШЕН</p>
            <p style="font-size: 12pt; color: #f7e9cc; margin-top: 15px;">Проводник: {{ character_name }} • {{ current_date }}</p>
        </div>
        <div style="position: absolute; bottom: 25mm; left: 0; right: 0; text-align: center;">
            <p style="font-size: 8pt; color: rgba(247, 233, 204, 0.4);">
                Диагностика судьбы исключительно в информационных целях
            </p>
        </div>
    </div>
</body>
</html>"""

GROUP_B_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 0;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: linear-gradient(rgba(8, 12, 20, 0.85), rgba(8, 12, 20, 0.85)), url('cards/uslugi/pdf_background_final.png') no-repeat center center; /* Тинт глубокого синего + общий мистический фон */
            background-size: cover;
            color: #e2ebf5;
        }
        .container {
            min-height: 100vh;
            position: relative;
            box-sizing: border-box;
        }
        .cover {
            height: 280mm;
            position: relative;
            padding-top: 40px;
            text-align: center;
        }
        .logo-top {
            display: block;
            width: 25%;
            margin: 0 auto 20px auto;
        }
        .biometry-img {
            display: block;
            max-width: 120mm;
            max-height: 120mm;
            margin: 30px auto;
            border-radius: 50%;
            border: 4px solid #a3c1ad;
            box-shadow: 0 0 35px rgba(163, 193, 173, 0.7);
        }
        .user-info-wrapper {
            position: absolute;
            bottom: 40mm;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(8, 12, 20, 0.9);
            padding: 20px 60px;
            border-radius: 12px;
            border: 2px solid #a3c1ad;
            box-shadow: 0 0 30px rgba(163, 193, 173, 0.4);
            min-width: 440px;
        }
        .user-info {
            font-size: 13pt;
            font-weight: 700;
            color: #c9daf8;
            line-height: 1.6;
        }
        .highlight { color: #ffffff; }

        .content-wrapper {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(163, 193, 173, 0.3);
            border-radius: 16px;
            padding: 40px 45px;
            margin: 40px 50px;
        }
        .content-title {
            font-size: 20pt;
            font-weight: 700;
            color: #a3c1ad;
            text-align: center;
            margin-bottom: 30px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .panel {
            background: rgba(22, 34, 57, 0.7);
            border-left: 4px solid #a3c1ad;
            border-radius: 8px;
            padding: 22px 26px;
            margin: 30px 0;
        }
        .panel h3 {
            font-size: 14pt;
            font-weight: 700;
            color: #c9daf8;
            margin-top: 0;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .panel p {
            font-size: 12pt;
            line-height: 1.65;
            margin: 0;
            text-align: justify;
        }
    </style>
</head>
<body>
    <div class="container cover">
        <img src="cards/uslugi/logo.png" class="logo-top" alt="Logo">
        {% if eye_photo %}
        <img src="{{ eye_photo }}" class="biometry-img" alt="Радужка">
        {% elif palm_photos and palm_photos[0] %}
        <img src="{{ palm_photos[0] }}" class="biometry-img" alt="Линии ладони">
        {% else %}
        <img src="cards/uslugi/head2.png" class="biometry-img" style="border-radius: 12px;" alt="Биометрия">
        {% endif %}
        <div class="user-info-wrapper">
            <div class="user-info">
                РИТУАЛ: <span class="highlight">{{ section_name }}</span><br>
                ИМЯ: <span class="highlight">{{ user_name }}</span><br>
                ТОЧКА ВХОДА: {{ birth_info }}
            </div>
        </div>
    </div>
    <div style="page-break-before: always;"></div>

    <div class="container">
        <div class="content-wrapper">
            <div class="content-title">Сакральный Читатель Проекций</div>

            {% if palm_photos and palm_photos[1] %}
            <div style="text-align: center; margin-bottom: 35px;">
                <img src="{{ palm_photos[1] }}" style="max-height: 80mm; border-radius: 8px; border: 2px solid #a3c1ad; box-shadow: 0 0 15px rgba(163,193,173,0.3);">
                <p style="font-size: 10pt; color: #a3c1ad; margin-top: 5px;">ПРАВАЯ ЛАДОНЬ (РЕАЛИЗАЦИЯ ПОТОКА)</p>
            </div>
            {% endif %}

            <div class="panel">
                <h3>1. Дешифровка Внешних Маркеров</h3>
                <p>{{ iris_or_line_decoding | safe }}</p>
            </div>

            <div class="panel">
                <h3>2. Сакральная Уязвимость и Блоки</h3>
                <p>{{ spiritual_vulnerability | safe }}</p>
            </div>

            <div class="panel">
                <h3>3. Вектор Раскрытия Интуиции</h3>
                <p>{{ intuition_unlk | safe }}</p>
            </div>

            <div class="panel">
                <h3>4. Практики Сонастройки</h3>
                <p>{{ daily_mudras | safe }}</p>
            </div>
        </div>
    </div>

    <div style="page-break-before: always;"></div>
    <div class="container" style="text-align: center; padding-top: 60mm; height: 280mm;">
        <div style="margin-bottom: 40px;">
            <img src="cards/uslugi/logo.png" style="width: 200px; display: block; margin: 0 auto;">
        </div>
        <div style="color: #c9daf8;">
            <p style="font-weight: 700; font-size: 18pt; letter-spacing: 2px;">ЧТЕНИЕ ПРОЕКЦИЙ ЗАВЕРШЕНО</p>
            <p style="font-size: 12pt; color: #e2ebf5; margin-top: 15px;">Проводник: {{ character_name }} • {{ current_date }}</p>
        </div>
        <div style="position: absolute; bottom: 25mm; left: 0; right: 0; text-align: center;">
            <p style="font-size: 8pt; color: rgba(226, 235, 245, 0.4);">
                Диагностика судьбы исключительно в информационных целях
            </p>
        </div>
    </div>
</body>
</html>"""

GROUP_C_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 0;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: linear-gradient(rgba(20, 13, 13, 0.85), rgba(20, 13, 13, 0.85)), url('cards/uslugi/pdf_background_final.png') no-repeat center center; /* Тинт древней бордо + общий мистический фон */
            background-size: cover;
            color: #fcece2;
        }
        .container {
            min-height: 100vh;
            position: relative;
            box-sizing: border-box;
        }
        .cover {
            height: 280mm;
            position: relative;
            padding-top: 40px;
            text-align: center;
        }
        .logo-top {
            display: block;
            width: 25%;
            margin: 0 auto 20px auto;
        }
        .oracle-img {
            display: block;
            max-width: 120mm;
            max-height: 120mm;
            margin: 30px auto;
            border-radius: 8px;
            border: 3px solid #df9a57;
            box-shadow: 0 0 35px rgba(223, 154, 87, 0.6);
        }
        .user-info-wrapper {
            position: absolute;
            bottom: 40mm;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(20, 13, 13, 0.9);
            padding: 20px 60px;
            border-radius: 12px;
            border: 2px solid #df9a57;
            box-shadow: 0 0 30px rgba(223, 154, 87, 0.4);
            min-width: 440px;
        }
        .user-info {
            font-size: 13pt;
            font-weight: 700;
            color: #f7c59f;
            line-height: 1.6;
        }
        .highlight { color: #ffffff; }

        .content-wrapper {
            background: rgba(36, 21, 21, 0.85);
            border: 1px solid rgba(223, 154, 87, 0.3);
            border-radius: 16px;
            padding: 40px 45px;
            margin: 40px 50px;
        }
        .content-title {
            font-size: 20pt;
            font-weight: 700;
            color: #df9a57;
            text-align: center;
            margin-bottom: 30px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .panel {
            background: rgba(48, 28, 28, 0.7);
            border-left: 4px solid #df9a57;
            border-radius: 8px;
            padding: 22px 26px;
            margin: 30px 0;
        }
        .panel h3 {
            font-size: 14pt;
            font-weight: 700;
            color: #f7c59f;
            margin-top: 0;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .panel p {
            font-size: 12pt;
            line-height: 1.65;
            margin: 0;
            text-align: justify;
        }
    </style>
</head>
<body>
    <div class="container cover">
        <img src="cards/uslugi/logo.png" class="logo-top" alt="Logo">
        <!-- FIX (аудит 2026-11-10): удален битый egypt_head.png - файла нет в cards/uslugi, WeasyPrint рисовал пустое место -->
        <div class="user-info-wrapper">
            <div class="user-info">
                РИТУАЛ: <span class="highlight">{{ section_name }}</span><br>
                ИМЯ: <span class="highlight">{{ user_name }}</span><br>
                ТОЧКА ВХОДА: {{ birth_info }}
            </div>
        </div>
    </div>
    <div style="page-break-before: always;"></div>

    <div class="container">
        <div class="content-wrapper">
            <div class="content-title">Древние Оракулы и Силы Духов</div>

            <div class="panel">
                <h3>1. Послание Древних Сил</h3>
                <p>{{ message_from_abyss | safe }}</p>
            </div>

            <div class="panel">
                <h3>2. Интеграция Скрытых Сил</h3>
                <p>{{ shadow_integration | safe }}</p>
            </div>

            <div class="panel">
                <h3>3. Сакральные Табу</h3>
                <p>{{ sacred_taboo | safe }}</p>
            </div>

            <div class="panel">
                <h3>4. Ритуал Сонастройки</h3>
                <p>{{ astral_totem_ritual | safe }}</p>
            </div>
        </div>
    </div>

    <div style="page-break-before: always;"></div>
    <div class="container" style="text-align: center; padding-top: 60mm; height: 280mm;">
        <div style="margin-bottom: 40px;">
            <img src="cards/uslugi/logo.png" style="width: 200px; display: block; margin: 0 auto;">
        </div>
        <div style="color: #f7c59f;">
            <p style="font-weight: 700; font-size: 18pt; letter-spacing: 2px;">РИТУАЛ ОРАКУЛА ЗАВЕРШЕН</p>
            <p style="font-size: 12pt; color: #fcece2; margin-top: 15px;">Проводник: {{ character_name }} • {{ current_date }}</p>
        </div>
        <div style="position: absolute; bottom: 25mm; left: 0; right: 0; text-align: center;">
            <p style="font-size: 8pt; color: rgba(252, 236, 226, 0.4);">
                Диагностика судьбы исключительно в информационных целях
            </p>
        </div>
    </div>
</body>
</html>"""

GROUP_D_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 0;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: linear-gradient(rgba(9, 9, 26, 0.85), rgba(9, 9, 26, 0.85)), url('cards/uslugi/pdf_background_final.png') no-repeat center center; /* Тинт космоса + общий мистический фон */
            background-size: cover;
            color: #e0f2f1;
        }
        .container {
            min-height: 100vh;
            position: relative;
            box-sizing: border-box;
        }
        .cover {
            height: 280mm;
            position: relative;
            padding-top: 40px;
            text-align: center;
        }
        .logo-top {
            display: block;
            width: 25%;
            margin: 0 auto 20px auto;
        }
        .astro-map-img {
            display: block;
            max-width: 120mm;
            max-height: 120mm;
            margin: 30px auto;
            border-radius: 12px;
            border: 2px solid #26a69a;
            box-shadow: 0 0 35px rgba(38, 166, 154, 0.5);
        }
        .user-info-wrapper {
            position: absolute;
            bottom: 40mm;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(9, 9, 26, 0.9);
            padding: 20px 60px;
            border-radius: 12px;
            border: 2px solid #26a69a;
            box-shadow: 0 0 30px rgba(38, 166, 154, 0.4);
            min-width: 440px;
        }
        .user-info {
            font-size: 13pt;
            font-weight: 700;
            color: #80cbc4;
            line-height: 1.6;
        }
        .highlight { color: #ffffff; }

        .content-wrapper {
            background: rgba(18, 18, 38, 0.85);
            border: 1px solid rgba(38, 166, 154, 0.3);
            border-radius: 16px;
            padding: 40px 45px;
            margin: 40px 50px;
        }
        .content-title {
            font-size: 20pt;
            font-weight: 700;
            color: #26a69a;
            text-align: center;
            margin-bottom: 30px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .badge {
            display: inline-block;
            background: #26a69a;
            color: #09091a;
            font-weight: 700;
            font-size: 11pt;
            padding: 6px 16px;
            border-radius: 20px;
            margin-bottom: 25px;
            text-transform: uppercase;
            letter-spacing: 1px;
            box-shadow: 0 0 15px rgba(38, 166, 154, 0.6);
        }
        .panel {
            background: rgba(27, 27, 54, 0.7);
            border-left: 4px solid #26a69a;
            border-radius: 8px;
            padding: 22px 26px;
            margin: 30px 0;
        }
        .panel h3 {
            font-size: 14pt;
            font-weight: 700;
            color: #80cbc4;
            margin-top: 0;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .panel p {
            font-size: 12pt;
            line-height: 1.65;
            margin: 0;
            text-align: justify;
        }
    </style>
</head>
<body>
    <div class="container cover">
        <img src="cards/uslugi/logo.png" class="logo-top" alt="Logo">
        <!-- FIX (аудит 2026-11-10): удален битый astro_map.png - файла нет в cards/uslugi -->
        <div class="user-info-wrapper">
            <div class="user-info">
                РИТУАЛ: <span class="highlight">{{ section_name }}</span><br>
                ИМЯ: <span class="highlight">{{ user_name }}</span><br>
                ТОЧКА ВХОДА: {{ birth_info }}
            </div>
        </div>
    </div>
    <div style="page-break-before: always;"></div>

    <div class="container">
        <div class="content-wrapper">
            <div class="content-title">Звездный Резонанс и Алхимия Сфер</div>

            {% if cosmic_frequency_status %}
            <div style="text-align: center;">
                <div class="badge">{{ cosmic_frequency_status }}</div>
            </div>
            {% endif %}

            <div class="panel">
                <h3>1. Резонанс Макрокосма</h3>
                <p>{{ macrocosm_resonance | safe }}</p>
            </div>

            <div class="panel">
                <h3>2. Формула Баланса</h3>
                <p>{{ balance_formula | safe }}</p>
            </div>

            <div class="panel">
                <h3>3. Ритуал Сонастройки</h3>
                <p>{{ space_alignment | safe }}</p>
            </div>
        </div>
    </div>

    <div style="page-break-before: always;"></div>
    <div class="container" style="text-align: center; padding-top: 60mm; height: 280mm;">
        <div style="margin-bottom: 40px;">
            <img src="cards/uslugi/logo.png" style="width: 200px; display: block; margin: 0 auto;">
        </div>
        <div style="color: #80cbc4;">
            <p style="font-weight: 700; font-size: 18pt; letter-spacing: 2px;">РЕЗОНАНС СФЕР ЗАФИКСИРОВАН</p>
            <p style="font-size: 12pt; color: #e0f2f1; margin-top: 15px;">Проводник: {{ character_name }} • {{ current_date }}</p>
        </div>
        <div style="position: absolute; bottom: 25mm; left: 0; right: 0; text-align: center;">
            <p style="font-size: 8pt; color: rgba(224, 242, 241, 0.4);">
                Диагностика судьбы исключительно в информационных целях
            </p>
        </div>
    </div>
</body>
</html>"""

GROUP_E_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 0;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: url('cards/uslugi/pdf_background_final.png') no-repeat center center;
            background-size: cover;
            color: #f0e6d2;
        }
        .container {
            min-height: 100vh;
            position: relative;
            box-sizing: border-box;
        }
        .cover {
            height: 280mm;
            position: relative;
            padding-top: 40px;
            text-align: center;
        }
        .logo-top {
            display: block;
            width: 28%;
            margin: 0 auto 10px auto;
        }
        .head-img {
            display: block;
            width: 100%;
            height: auto;
            max-height: 180mm;
            object-fit: contain;
            margin: 0 auto;
        }
        .user-info-wrapper {
            position: absolute;
            bottom: 40mm;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(20, 15, 35, 0.85);
            padding: 18px 75px;
            border-radius: 16px;
            box-shadow: 0 0 45px rgba(212, 175, 55, 0.78);
            min-width: 460px;
            max-width: 520px;
        }
        .user-info {
            font-size: 14pt;
            font-weight: 700;
            color: #f4d48c;
            line-height: 1.65;
            letter-spacing: 0.5px;
        }
        .highlight { color: #ffe8a3; }

        .content-wrapper {
            background: rgba(20, 15, 35, 0.7);
            border-radius: 20px;
            padding: 45px 50px;
            margin: 60px 50px;
            box-shadow: 0 12px 45px rgba(0,0,0,0.7);
        }
        .content-title {
            font-size: 22pt;
            font-weight: 700;
            color: #f4d48c;
            text-align: center;
            margin-bottom: 30px;
            letter-spacing: 1.6px;
            text-transform: uppercase;
        }
        .panel {
            background: rgba(30, 20, 45, 0.6);
            border-radius: 16px;
            padding: 26px 30px;
            margin: 42px 0;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
        }
        .panel h3 {
            font-size: 14pt;
            font-weight: 700;
            color: #ffe8a3;
            margin-top: 0;
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .panel p {
            font-size: 16pt;
            line-height: 1.6;
            margin: 0;
            text-align: justify;
        }
        .card-container {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 59vh;
            margin: 100px 0 75px 0;
            text-align: center;
            page-break-inside: avoid;
        }
        .card-background {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 435px;
            z-index: 3;
        }
        .card-image {
            position: relative;
            max-width: 298px;
            z-index: 2;
        }
        .card-info {
            text-align: center;
            margin-top: 40px;
            margin-bottom: 40px;
            color: #f4d48c;
            font-size: 14.5pt;
        }
        .card-name {
            font-weight: 700;
            font-size: 22pt;
            margin-bottom: 16px;
            letter-spacing: 1.6px;
        }
        .affirmations-list {
            margin: 15px 0 0 0;
            padding-left: 20px;
        }
        .affirmations-list li {
            font-size: 13pt;
            color: #ffe8a3;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container cover">
        <img src="cards/uslugi/logo.png" class="logo-top" alt="Logo">
        <!-- FIX (аудит 2026-11-10): удален битый taro_head.png - файла нет в cards/uslugi -->
        <div class="user-info-wrapper">
            <div class="user-info">
                РИТУАЛ: <span class="highlight">{{ section_name }}</span><br>
                ИМЯ: <span class="highlight">{{ user_name }}</span><br>
                ТОЧКА ВХОДА: {{ birth_info }}
            </div>
        </div>
    </div>
    <div style="page-break-before: always;"></div>

    <div class="container">
        <div class="content-wrapper">
            <div class="content-title">Разбор Арканов Таро</div>

            {% if tarot_arcana_analysis %}
            <div class="panel">
                <h3>1. Глубокий Разбор Арканов</h3>
                <p>{{ tarot_arcana_analysis | safe }}</p>
            </div>
            {% elif text_content %}
            <div class="panel">
                <h3>Сакральное Толкование</h3>
                <p>{{ text_content | safe }}</p>
            </div>
            {% endif %}

            {% if card_image_path %}
            <div class="card-container">
                <img src="cards/uslugi/bac.png" class="card-background">
                <img src="{{ card_image_path }}" class="card-image">
            </div>
            <div class="card-info">
                <div class="card-name">{{ card_name }}</div>
                <p>{{ card_description | safe }}</p>
            </div>
            {% endif %}

            {% if karmic_lesson %}
            <div class="panel">
                <h3>2. Кармический Урок Ситуации</h3>
                <p>{{ karmic_lesson | safe }}</p>
            </div>
            {% endif %}

            {% if energy_alignment_tips %}
            <div class="panel">
                <h3>3. Советы по Выравниванию Энергии</h3>
                <p>{{ energy_alignment_tips | safe }}</p>
            </div>
            {% endif %}

            {% if daily_affirmations %}
            <div class="panel">
                <h3>4. Сакральные Аффирмации</h3>
                <ul class="affirmations-list">
                    {{ daily_affirmations | safe }}
                </ul>
            </div>
            {% endif %}
        </div>
    </div>

    <div style="page-break-before: always;"></div>
    <div class="container" style="text-align: center; padding-top: 60mm; height: 280mm;">
        <div style="margin-bottom: 40px;">
            <img src="cards/uslugi/logo.png" style="width: 200px; display: block; margin: 0 auto;">
        </div>
        <div style="color: #f4d48c;">
            <p style="font-weight: 700; font-size: 18pt; letter-spacing: 2px;">РИТУАЛ ТАРО ЗАВЕРШЕН</p>
            <p style="font-size: 13pt; color: #ffe8a3; margin-top: 15px;">Проводник: {{ character_name }} • {{ current_date }}</p>
        </div>
        <div style="position: absolute; bottom: 25mm; left: 0; right: 0; text-align: center;">
            <p style="font-size: 8pt; color: rgba(240, 230, 210, 0.4);">
                Диагностика судьбы исключительно в информационных целях
            </p>
        </div>
    </div>
</body>
</html>"""

# Специализированный премиальный шаблон для сакральных многокарточных раскладов Таро
TAROT_SPREAD_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'Lora';
            src: url('Lora-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        @page {
            size: A4;
            margin: 15mm 15mm 18mm 15mm;
            @bottom-right {
                content: counter(page);
                font-family: 'Lora', serif;
                font-size: 8.5pt;
                color: rgba(212, 175, 55, 0.5);
            }
        }
        @page :first {
            margin: 0;
            @bottom-right {
                content: none;
            }
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Lora', serif;
            background: #110b17 url('cards/uslugi/pdf_background_final.png') repeat-y center top;
            background-size: 100% auto;
            color: #f2e7d5;
            -webkit-print-color-adjust: exact;
        }
        .container {
            position: relative;
            box-sizing: border-box;
        }
        
        /* ---------------- COVER PAGE ---------------- */
        .cover {
            height: 297mm;
            position: relative;
            text-align: center;
            box-sizing: border-box;
            padding-top: 25px;
            page-break-inside: avoid;
            overflow: hidden;
        }
        .cover-logo {
            display: block;
            width: 22%;
            max-width: 120px;
            margin: 0 auto 10px auto;
        }
        .cover-art-box {
            margin: 10px auto 18px auto;
            text-align: center;
        }
        .cover-art {
            max-width: 95mm;
            max-height: 95mm;
            border-radius: 14px;
            border: 3px solid #d4af37;
            box-shadow: 0 0 35px rgba(212, 175, 55, 0.55);
            object-fit: contain;
            display: inline-block;
        }
        .cover-badge {
            background: rgba(18, 12, 28, 0.9);
            border: 2px solid #d4af37;
            border-radius: 14px;
            box-shadow: 0 0 35px rgba(212, 175, 55, 0.45);
            padding: 16px 36px;
            margin: 0 auto;
            max-width: 500px;
        }
        .cover-ritual-type {
            font-size: 11pt;
            letter-spacing: 3px;
            color: #d4af37;
            text-transform: uppercase;
            margin-bottom: 6px;
            font-weight: 700;
        }
        .cover-title {
            font-size: 18pt;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: 1.2px;
            margin-bottom: 10px;
            text-transform: uppercase;
            text-shadow: 0 0 15px rgba(212, 175, 55, 0.6);
        }
        .cover-divider {
            color: #d4af37;
            letter-spacing: 6px;
            font-size: 12pt;
            margin-bottom: 12px;
        }
        .cover-meta {
            font-size: 11pt;
            line-height: 1.7;
            color: #e5d7c3;
        }
        .cover-meta strong {
            color: #ffe8a3;
        }

        /* ---------------- SECTION HEADERS ---------------- */
        .page-header {
            text-align: center;
            margin: 15px 0 25px 0;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(212, 175, 55, 0.35);
        }
        .page-header-title {
            font-size: 19pt;
            font-weight: 700;
            color: #d4af37;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 6px;
            text-shadow: 0 0 12px rgba(212, 175, 55, 0.4);
        }
        .page-header-sub {
            font-size: 10.5pt;
            font-style: italic;
            color: #c9bca9;
            letter-spacing: 0.5px;
        }

        /* ---------------- CARDS GALLERY / OVERVIEW ---------------- */
        .cards-grid {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 12px;
            margin: 15px 0 25px 0;
        }
        .card-cell {
            background: rgba(25, 18, 38, 0.78);
            border: 1px solid rgba(212, 175, 55, 0.4);
            border-radius: 10px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.55);
            padding: 10px 8px;
            text-align: center;
            box-sizing: border-box;
            page-break-inside: avoid;
        }
        .grid-count-3 .card-cell { width: 31%; }
        .grid-count-4 .card-cell { width: 23%; }
        .grid-count-5 .card-cell { width: 31%; }
        .grid-count-6 .card-cell { width: 31%; }
        .grid-count-7 .card-cell,
        .grid-count-8 .card-cell { width: 23%; }
        .grid-count-9 .card-cell,
        .grid-count-10 .card-cell { width: 18.5%; }

        .card-cell-pos {
            font-size: 8pt;
            font-weight: 700;
            color: #d4af37;
            text-transform: uppercase;
            line-height: 1.3;
            margin-bottom: 6px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        .card-cell-img {
            max-height: 48mm;
            width: auto;
            max-width: 90%;
            border-radius: 6px;
            border: 1px solid #d4af37;
            box-shadow: 0 0 10px rgba(212, 175, 55, 0.35);
            display: block;
            margin: 0 auto 6px auto;
        }
        .card-cell-name {
            font-size: 9pt;
            font-weight: 700;
            color: #ffffff;
            margin-top: 4px;
            line-height: 1.25;
        }
        .card-cell-sub {
            font-size: 7.5pt;
            color: #c9bca9;
            font-style: italic;
            margin-top: 2px;
        }

        /* ---------------- READING CONTENT ---------------- */
        .prologue-box {
            background: rgba(30, 20, 45, 0.7);
            border-left: 4px solid #d4af37;
            border-radius: 10px;
            padding: 18px 24px;
            margin-bottom: 25px;
            font-size: 11pt;
            font-style: italic;
            line-height: 1.7;
            color: #ffe8a3;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
            page-break-inside: avoid;
        }
        .prologue-header {
            font-style: normal;
            font-weight: 700;
            font-size: 10.5pt;
            letter-spacing: 1px;
            color: #d4af37;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .reading-panel {
            background: rgba(24, 16, 36, 0.8);
            border: 1px solid rgba(212, 175, 55, 0.35);
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 22px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.55);
            page-break-inside: avoid;
        }
        .reading-panel-header {
            display: flex;
            align-items: center;
            border-bottom: 1px solid rgba(212, 175, 55, 0.25);
            padding-bottom: 10px;
            margin-bottom: 14px;
        }
        .reading-panel-badge {
            background: #d4af37;
            color: #120c18;
            font-weight: 700;
            font-size: 11pt;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            display: inline-block;
            text-align: center;
            line-height: 26px;
            margin-right: 12px;
            flex-shrink: 0;
        }
        .reading-panel-title {
            font-size: 12.5pt;
            font-weight: 700;
            color: #ffe8a3;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .reading-panel-arcana {
            color: #ffffff;
            font-weight: 700;
            font-size: 12pt;
            margin-left: 6px;
        }
        .reading-panel-body {
            font-size: 11pt;
            line-height: 1.7;
            text-align: justify;
            color: #f2e7d5;
        }
        .reading-panel-body p {
            margin: 0 0 10px 0;
        }
        .reading-panel-body p:last-child {
            margin-bottom: 0;
        }

        /* ---------------- SYNTHESIS & ADVICE ---------------- */
        .synthesis-panel {
            background: linear-gradient(135deg, rgba(45, 30, 65, 0.85), rgba(25, 15, 40, 0.9));
            border: 2px solid #d4af37;
            border-radius: 14px;
            padding: 24px 28px;
            margin: 30px 0 25px 0;
            box-shadow: 0 0 30px rgba(212, 175, 55, 0.35);
            page-break-inside: avoid;
        }
        .synthesis-header {
            text-align: center;
            font-size: 13.5pt;
            font-weight: 700;
            color: #ffe8a3;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            margin-bottom: 14px;
            border-bottom: 1px solid rgba(212, 175, 55, 0.3);
            padding-bottom: 10px;
        }
        .synthesis-header span {
            color: #d4af37;
            margin-right: 6px;
        }
        .synthesis-body {
            font-size: 11.5pt;
            line-height: 1.75;
            text-align: justify;
            color: #ffffff;
        }

        /* ---------------- FINAL PAGE ---------------- */
        .final-page {
            min-height: 220mm;
            text-align: center;
            box-sizing: border-box;
            padding-top: 40mm;
            position: relative;
            page-break-inside: avoid;
        }
        .final-logo {
            width: 170px;
            display: block;
            margin: 0 auto 35px auto;
        }
        .final-seal {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            border: 2px solid #d4af37;
            margin: 0 auto 30px auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 35px rgba(212, 175, 55, 0.4);
            background: rgba(25, 18, 38, 0.85);
        }
        .final-seal-icon {
            font-size: 26pt;
            color: #d4af37;
            line-height: 1;
            margin-bottom: 4px;
        }
        .final-seal-text {
            font-size: 8pt;
            font-weight: 700;
            letter-spacing: 1.5px;
            color: #ffe8a3;
            text-transform: uppercase;
        }
        .final-quote {
            font-size: 12.5pt;
            font-style: italic;
            color: #ffe8a3;
            max-width: 480px;
            margin: 0 auto 15px auto;
            line-height: 1.65;
        }
        .final-guide {
            font-size: 11.5pt;
            color: #d4af37;
            font-weight: 700;
            letter-spacing: 1px;
            margin-bottom: 6px;
        }
        .final-date {
            font-size: 9.5pt;
            color: #a89a87;
        }
        .final-disclaimer {
            position: absolute;
            bottom: 12mm;
            left: 0;
            right: 0;
            font-size: 8pt;
            color: rgba(240, 230, 210, 0.45);
            letter-spacing: 0.5px;
        }
    </style>
</head>
<body>
    <!-- 1. COVER PAGE -->
    <div class="cover">
        <img src="cards/uslugi/logo.png" class="cover-logo" alt="Logo">
        {% if spread_cover %}
        <div class="cover-art-box">
            <img src="{{ spread_cover }}" class="cover-art" alt="">
        </div>
        {% endif %}
        <div class="cover-badge">
            <div class="cover-ritual-type">САКРАЛЬНЫЙ РАСКЛАД ТАРО</div>
            <div class="cover-title">«{{ spread_title }}»</div>
            <div class="cover-divider">✦ ✦ ✦</div>
            <div class="cover-meta">
                <div>ВОПРОШАЮЩИЙ: <strong>{{ user_name }}</strong></div>
                <div>ТОЧКА ВХОДА: <strong>{{ birth_info }}</strong></div>
                <div>ПРОВОДНИК: <strong>{{ character_name }}</strong> • {{ current_date }}</div>
            </div>
        </div>
    </div>

    <!-- 2. CARDS GALLERY / OVERVIEW PAGE -->
    {% if cards_list and cards_list|length > 0 %}
    <div style="page-break-before: always;"></div>
    <div class="container">
        <div class="page-header">
            <div class="page-header-title">СВЯЩЕННАЯ КАРТА РАСКЛАДА</div>
            <div class="page-header-sub">Выпавшие Арканы судьбы и их сакральные позиции в круге таинства</div>
        </div>
        <div class="cards-grid grid-count-{{ cards_list|length }}">
            {% for c in cards_list %}
            <div class="card-cell">
                <div class="card-cell-pos">{{ c.pos_title }}</div>
                <img src="{{ c.img_path }}" class="card-cell-img" alt="{{ c.name }}">
                <div class="card-cell-name">{{ c.name }}</div>
                {% if c.subtitle %}
                <div class="card-cell-sub">{{ c.subtitle }}</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- 3. DETAILED READING PAGES -->
    <div style="page-break-before: always;"></div>
    <div class="container">
        <div class="page-header">
            <div class="page-header-title">ТАИНСТВО ТОЛКОВАНИЯ</div>
            <div class="page-header-sub">Глубинный разбор позиций и сакральный резонанс вашей ситуации</div>
        </div>

        {% if prologue %}
        <div class="prologue-box">
            <div class="prologue-header">✦ СЛОВО ПРОВОДНИКА ({{ character_name }}) ✦</div>
            <div>{{ prologue | safe }}</div>
        </div>
        {% endif %}

        {% if sections and sections|length > 0 %}
            {% for s in sections %}
            <div class="reading-panel">
                <div class="reading-panel-header">
                    <span class="reading-panel-badge">{{ s.num if s.num else loop.index }}</span>
                    <div>
                        <span class="reading-panel-title">{{ s.title }}</span>
                        {% if s.card_name %}
                        <span class="reading-panel-arcana">— «{{ s.card_name }}»</span>
                        {% endif %}
                    </div>
                </div>
                <div class="reading-panel-body">
                    <p>{{ s.content | safe }}</p>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="reading-panel">
                <div class="reading-panel-header">
                    <span class="reading-panel-badge">✦</span>
                    <span class="reading-panel-title">САКРАЛЬНОЕ ТОЛКОВАНИЕ</span>
                </div>
                <div class="reading-panel-body">
                    {{ formatted_full_text | safe }}
                </div>
            </div>
        {% endif %}

        {% if synthesis %}
        <div class="synthesis-panel">
            <div class="synthesis-header">
                <span>✦</span> СИНТЕЗ КАРТ И САКРАЛЬНЫЙ СОВЕТ <span>✦</span>
            </div>
            <div class="synthesis-body">
                <p>{{ synthesis | safe }}</p>
            </div>
        </div>
        {% endif %}
    </div>

    <!-- 4. FINAL PAGE -->
    <div style="page-break-before: always;"></div>
    <div class="final-page">
        <img src="cards/uslugi/logo.png" class="final-logo" alt="Logo">
        <div class="final-seal">
            <div class="final-seal-icon">✦</div>
            <div class="final-seal-text">РИТУАЛ ЗАВЕРШЕН</div>
        </div>
        <div class="final-quote">
            «Пусть знаки Арканов осветят твой путь в лабиринте времени, а воля твоя пребудет твердой, как алмаз.»
        </div>
        <div class="final-guide">— Твой Проводник, {{ character_name }}</div>
        <div class="final-date">{{ current_date }} • Печать Анти-Тар</div>
        <div class="final-disclaimer">
            Диагностика судьбы носит сакрально-информационный характер • Храни это знание бережно
        </div>
    </div>
</body>
</html>"""

def get_html_template(section: str) -> str:
    from prompts.services import SERVICE_GROUP_MAP
    from configs.tarot_spreads import TAROT_SPREAD_KEYS

    s_clean = section.lower().strip()
    if s_clean in TAROT_SPREAD_KEYS or s_clean.startswith("tarot_"):
        return TAROT_SPREAD_TEMPLATE

    group = SERVICE_GROUP_MAP.get(s_clean, "E")
    if group == "A":
        return GROUP_A_TEMPLATE
    elif group == "B":
        return GROUP_B_TEMPLATE
    elif group == "C":
        return GROUP_C_TEMPLATE
    elif group == "D":
        return GROUP_D_TEMPLATE
    else:
        return GROUP_E_TEMPLATE
