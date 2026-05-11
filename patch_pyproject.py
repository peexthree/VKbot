
with open('pyproject.toml', 'r', encoding='utf-8') as f:
    content = f.read()

# Make a minor change to trigger poetry install if needed
content = content.replace('vkbottle = "4.3.12"', 'vkbottle = "4.3.12"')

with open('pyproject.toml', 'w', encoding='utf-8') as f:
    f.write(content)
