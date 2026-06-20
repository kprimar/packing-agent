import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def _load() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    with open(_CONFIG_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def get_default_location() -> str | None:
    return _load().get('default_location')


def set_default_location(location: str):
    config = _load()
    config['default_location'] = location.strip()
    _save(config)


def clear_default_location():
    config = _load()
    config.pop('default_location', None)
    _save(config)


def get_work_days() -> list[str]:
    return _load().get('work_days', [])


def set_work_days(days: list[str]):
    config = _load()
    config['work_days'] = days
    _save(config)


def get_dress_code() -> str | None:
    return _load().get('dress_code')


def set_dress_code(code: str):
    config = _load()
    config['dress_code'] = code
    _save(config)
