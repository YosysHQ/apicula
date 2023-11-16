import importlib.resources
import json

def replace_family_alias(family):
    with importlib.resources.path('apycula', f'family_info.json') as path:
        with open(path, 'r') as f:
            family_info = json.load(f)

    if family in family_info:
        return family_info[family]["base_family"]
    else:
        return family

