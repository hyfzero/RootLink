from pathlib import Path
import importlib
import sys


ROOT_DIR = Path(__file__).resolve().parent
SEARCH_DIRS = [
    ROOT_DIR,
    Path.cwd(),
    Path("/data/user/0/com.amadues.companion/files/flet"),
    Path("/data/data/com.amadues.companion/files/flet"),
]


def _add_import_path(path: Path) -> None:
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _candidate_roots(base: Path) -> list[Path]:
    roots = [base]
    if base.exists() and base.is_dir():
        roots.extend(path.parent.parent for path in base.glob("app*/GUI/app.py"))
        roots.extend(path for path in base.glob("**/app.zip"))
    return roots


for search_dir in SEARCH_DIRS:
    for root in _candidate_roots(search_dir):
        _add_import_path(root)
        _add_import_path(root / "src")
importlib.invalidate_caches()


def _debug_import_state() -> str:
    details = [f"__file__={__file__}", f"cwd={Path.cwd()}", f"sys.path={sys.path[:12]}"]
    for search_dir in SEARCH_DIRS:
        if search_dir.exists() and search_dir.is_dir():
            try:
                children = sorted(child.name for child in search_dir.iterdir())[:30]
            except OSError as exc:
                children = [f"<list failed: {exc}>"]
            details.append(f"{search_dir}={children}")
        else:
            details.append(f"{search_dir}=<missing>")
    return "\n".join(details)


try:
    from GUI.app import main
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(f"{exc}\n{_debug_import_state()}") from exc


if __name__ == "__main__":
    main()
