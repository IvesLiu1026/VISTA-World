"""Shared exact-slot material matching for Blender and Unreal authoring."""


def match_slot(name, candidates):
    return next((key for key in sorted(candidates, key=len, reverse=True)
                 if name == key or name.startswith(key + '_') or name.startswith(key + '.')), None)


def resolve_rule(label, name, plan):
    key = match_slot(name, plan['bindings'])
    if key is None:
        return None
    for override in plan['overrides']:
        if override['label_contains'] in label.lower() and key in override['slots']:
            return override['profile']
    return plan['bindings'][key]
