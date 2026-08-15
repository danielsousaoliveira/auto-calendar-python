import importlib
import pkgutil

import src


def test_all_package_modules_are_importable():
    module_names = [src.__name__]
    module_names.extend(module.name for module in pkgutil.walk_packages(src.__path__, "src."))

    for module_name in module_names:
        importlib.import_module(module_name)
