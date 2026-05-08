with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("from modules.utils import MockMsg, (", "from modules.utils import MockMsg\nfrom modules.utils import (")

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
