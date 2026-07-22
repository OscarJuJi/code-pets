"""Workspace scan: code files (any language) modified today, grouped by extension."""

import os
from datetime import date, datetime

CODE_EXTENSIONS = {
    ".py", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".c", ".h", ".cpp", ".cu",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".scss",
    ".sql", ".sh", ".ps1", ".md",
}
EXCLUDED_DIRS = {
    "node_modules", "venv", ".venv", "build", "dist", "__pycache__",
    "output", "~", "env",
}


def scan(root, today=None):
    """Return {"files": [relative paths modified today], "by_language": {ext: count}}."""
    today = today or date.today()
    day_start = datetime(today.year, today.month, today.day).timestamp()
    files = []
    by_language = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # prune in place: skip junk and every dot-directory (.git, .claude, ...)
        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, filename)
            try:
                if os.path.getmtime(full) >= day_start:
                    files.append(os.path.relpath(full, root))
                    by_language[ext] = by_language.get(ext, 0) + 1
            except OSError:
                continue
    return {"files": files, "by_language": by_language}
