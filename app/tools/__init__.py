"""
工具自动发现器：
导入 tools 包时，自动扫描本目录下所有 .py 模块并 import，
让各模块内的 @tool 装饰器完成注册。

新增工具：在本目录创建一个 .py 文件并使用 @tool 装饰器即可，
无需修改 main.py 或其他任何文件。
"""

import importlib
import pkgutil
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent

# 扫描本目录下所有非 _ 开头的模块
for module_info in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
    name = module_info.name
    if name.startswith("_"):
        continue
    importlib.import_module(f"{__name__}.{name}")
