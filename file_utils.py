import re
from pathlib import Path
from urllib.parse import unquote


def clean_filename(name):
    """
    Čisti naziv fajla da bude validan za Windows.
    """
    name = str(name).strip()
    name = unquote(name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name


def unique_path(path):
    """
    Ako fajl već postoji, dodaje _2, _3, _4...
    """
    path = Path(path)

    if not path.exists():
        return path

    parent = path.parent
    stem = path.stem
    suffix = path.suffix

    counter = 2

    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1