import re

with open('main.py', 'r') as f:
    content = f.read()

# We need to make sure the check handles the new text properly
button_logic_regex = r'if user_text\.lower\(\) == "не знаю время":'
new_button_logic = 'if user_text.lower() == "не знаю время" or user_text.lower() == "не знаю время (12:00)":'

content = re.sub(button_logic_regex, new_button_logic, content)

with open('main.py', 'w') as f:
    f.write(content)
