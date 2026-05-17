# ast_shim.py — Python 3.14 compatibility for old AST
import ast
import sys

if sys.version_info >= (3, 14):
    # Создаём алиасы для старых классов
    ast.Num = ast.Constant
    ast.Str = ast.Constant
    ast.Bytes = ast.Constant
    ast.NameConstant = ast.Constant
    ast.Ellipsis = ast.Constant

    # Пробрасываем старые атрибуты
    original_init = ast.Constant.__init__

    def patched_init(self, value, *args, **kwargs):
        original_init(self, value, *args, **kwargs)
        if isinstance(value, (int, float, complex)):
            self.n = value          # для Num
        elif isinstance(value, str):
            self.s = value          # для Str
        elif isinstance(value, bytes):
            self.s = value          # для Bytes
        # NameConstant: True/False/None
        elif value is True or value is False or value is None:
            self.value = value

    ast.Constant.__init__ = patched_init
