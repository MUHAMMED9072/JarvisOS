import importlib

class SkillInstaller:

    def install(self, module_name:str):
        return importlib.import_module(module_name)
