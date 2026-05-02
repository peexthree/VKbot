import re

with open("main.py", "r") as f:
    text = f.read()

# Fix the newline literals that got translated into actual newlines during re.sub
text = text.replace('\n\n{full_text}', '\\n\\n{full_text}')

with open("main.py", "w") as f:
    f.write(text)
