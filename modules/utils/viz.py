import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from loguru import logger
from modules.utils.astro import SIGNS_RU

# Настройка шрифта для поддержки кириллицы и символов
plt.rcParams['font.family'] = 'DejaVu Sans' # DejaVu Sans usually has better Unicode support

PLANET_SYMBOLS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆", "Pluto": "♇",
    "Mean Node": "☊"
}

def generate_natal_wheel(astro_data: dict, output_path: str):
    """
    Генерирует графическое изображение натальной карты.
    """
    try:
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'projection': 'polar'})
        ax.set_theta_direction(-1) # По часовой стрелке
        ax.set_theta_offset(np.pi) # Начинаем с Овна

        # Отрисовка знаков зодиака
        for i in range(12):
            theta_mid = np.deg2rad(i * 30 + 15)
            ax.text(theta_mid, 1.15, SIGNS_RU[i], ha='center', va='center', fontsize=9)
            # Границы знаков
            ax.plot([np.deg2rad(i * 30), np.deg2rad(i * 30)], [0.9, 1.2], color='black', linewidth=0.8)

        # Отрисовка планет
        for p_name, p_data in astro_data["planets"].items():
            lon = p_data["lon"]
            theta = np.deg2rad(lon)
            symbol = PLANET_SYMBOLS.get(p_name, p_name[0])
            # Смещаем немного радиус чтобы не перекрывать дома
            ax.text(theta, 0.95, symbol, ha='center', va='center', fontsize=16)
            ax.plot(theta, 1.0, 'o', color='gold', markersize=5, markeredgecolor='black')

        # Отрисовка аспектов (прямыми линиями)
        for aspect in astro_data["aspects"]:
            p1 = aspect["p1"]
            p2 = aspect["p2"]
            lon1 = astro_data["planets"][p1]["lon"]
            lon2 = astro_data["planets"][p2]["lon"]

            theta1 = np.deg2rad(lon1)
            theta2 = np.deg2rad(lon2)

            color = 'blue' if aspect["type"] in ["Trine", "Sextile"] else 'red'
            if aspect["type"] == "Conjunction": continue

            # Для рисования ПРЯМОЙ линии в полярных координатах matplotlib
            # нужно перевести в Декартовы, нарисовать, или просто использовать r=0 в центре.
            # Мы соединим планеты через центр или хордой.
            # Matplotlib.plot в полярке рисует дугу если r одинаковый.
            # Чтобы нарисовать прямую, нужно много точек.

            t = np.linspace(theta1, theta2, 50)
            # Линейная интерполяция в декартовых координатах для прямой линии
            x1, y1 = 0.8 * np.cos(theta1), 0.8 * np.sin(theta1)
            x2, y2 = 0.8 * np.cos(theta2), 0.8 * np.sin(theta2)

            # Но проще использовать ax.annotate с пустым текстом и стрелкой без головы (line)
            # или просто нарисовать в декартовых координатах поверх.
            # Но мы сделаем проще: нарисуем линию в декартовых координатах.
            pass

        # Перерисуем аспекты более правильно
        for aspect in astro_data["aspects"]:
            if aspect["type"] == "Conjunction": continue
            p1, p2 = aspect["p1"], aspect["p2"]
            theta1, theta2 = np.deg2rad(astro_data["planets"][p1]["lon"]), np.deg2rad(astro_data["planets"][p2]["lon"])
            color = 'blue' if aspect["type"] in ["Trine", "Sextile"] else 'red'

            # Параметрическое уравнение прямой в полярных координатах (через декартовы)
            r_val = 0.8
            x = [r_val * np.cos(theta1), r_val * np.cos(theta2)]
            y = [r_val * np.sin(theta1), r_val * np.sin(theta2)]

            # Конвертируем обратно в полярные для ax.plot
            thetas = np.arctan2(y, x)
            rs = np.sqrt(np.array(x)**2 + np.array(y)**2)
            ax.plot(thetas, rs, color=color, alpha=0.4, linewidth=1.2)

        # Отрисовка домов
        for h_num, h_data in astro_data["houses"].items():
            theta = np.deg2rad(h_data["lon"])
            ax.plot([theta, theta], [0, 0.9], color='darkblue', linewidth=1, alpha=0.6)
            ax.text(theta, 0.7, str(h_num), fontsize=8, ha='center', va='center', bbox={"facecolor": "white", "alpha": 0.5, "edgecolor": "none"})

        ax.set_yticklabels([])
        ax.set_xticklabels([])
        ax.spines['polar'].set_visible(True)
        ax.spines['polar'].set_color('black')
        ax.grid(False)

        plt.savefig(output_path, bbox_inches='tight', transparent=True, dpi=150)
        plt.close()
        return True
    except Exception as e:
        logger.error(f"Error generating natal wheel: {e}")
        return False
