import importlib
import pkgutil
import ast
from pathlib import Path

import src


def test_all_package_modules_are_importable():
    module_names = [src.__name__]
    module_names.extend(module.name for module in pkgutil.walk_packages(src.__path__, "src."))

    for module_name in module_names:
        importlib.import_module(module_name)


def test_scheduler_imports_no_network_capable_modules():
    tree = ast.parse(Path("src/scheduler.py").read_text())
    imports = {
        node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imports.isdisjoint({"google", "googleapiclient", "requests", "urllib3"})
