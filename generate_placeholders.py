import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs('assets/fallback_images', exist_ok=True)

# Generate 5 dark tarot-like minimalistic placeholder images
colors = ['#1A1A1A', '#2A2A2A', '#1C1C1C', '#222222', '#2E2B2A']
for i, color in enumerate(colors):
    img = Image.new('RGB', (1024, 1024), color=color)
    draw = ImageDraw.Draw(img)

    # Draw some random minimalistic geometry lines in dark gold
    gold = '#A67C00'
    draw.rectangle([100, 100, 924, 924], outline=gold, width=4)
    draw.ellipse([300, 300, 724, 724], outline=gold, width=2)
    draw.line([100, 100, 924, 924], fill=gold, width=1)
    draw.line([924, 100, 100, 924], fill=gold, width=1)

    img.save(f'assets/fallback_images/fallback_{i}.jpeg', format='JPEG')

print("Created 5 fallback images.")
