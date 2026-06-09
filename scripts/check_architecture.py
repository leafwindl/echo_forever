import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURES_ROOT = PROJECT_ROOT / "Echo-backend" / "features"
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
REMOVED_COMPAT_PATHS = (
    BACKEND_ROOT / "services",
    BACKEND_ROOT / "api",
    BACKEND_ROOT / "schemas",
    BACKEND_ROOT / "config.py",
    BACKEND_ROOT / "llm_client.py",
)

DOMAIN_BLOCKED_PREFIXES = (
    "api",
    "config",
    "db",
    "fastapi",
    "httpx",
    "pydantic",
    "providers",
    "repositories",
    "schemas",
    "services",
    "shared.config",
    "sqlite3",
)
APPLICATION_BLOCKED_PREFIXES = (
    "api",
    "config",
    "db",
    "fastapi",
    "httpx",
    "providers",
    "repositories",
    "schemas",
    "shared.config",
    "sqlite3",
)
INFRASTRUCTURE_BLOCKED_PREFIXES = (
    "api",
    "config",
    "fastapi",
    "schemas",
    "services",
)
INTERFACE_BLOCKED_PREFIXES = (
    "config",
    "db",
    "providers",
    "repositories",
    "services",
)


def _module_name(import_node: ast.AST) -> str:
    if isinstance(import_node, ast.Import):
        return ""
    if isinstance(import_node, ast.ImportFrom):
        return import_node.module or ""
    return ""


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    modules: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            modules.append((node.lineno, _module_name(node)))
    return modules


def _layer_for_path(path: Path) -> str:
    parts = path.relative_to(FEATURES_ROOT).parts
    for layer in ("domain", "application", "interface", "infrastructure"):
        if layer in parts:
            return layer
    return ""


def _is_blocked(module_name: str, blocked_prefixes: tuple[str, ...]) -> bool:
    return any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in blocked_prefixes)


def _blocked_prefixes_for_layer(layer: str) -> tuple[str, ...]:
    if layer == "domain":
        return DOMAIN_BLOCKED_PREFIXES
    if layer == "application":
        return APPLICATION_BLOCKED_PREFIXES
    if layer == "infrastructure":
        return INFRASTRUCTURE_BLOCKED_PREFIXES
    if layer == "interface":
        return INTERFACE_BLOCKED_PREFIXES
    return ()


def check_removed_compat_paths() -> list[str]:
    errors = []
    for path in REMOVED_COMPAT_PATHS:
        if path.is_file():
            errors.append(f"{path.relative_to(PROJECT_ROOT)}: removed compatibility file must not exist")
        elif path.is_dir() and any(path.rglob("*.py")):
            errors.append(f"{path.relative_to(PROJECT_ROOT)}: removed compatibility package must not contain Python files")
    return errors


def check_file(path: Path) -> list[str]:
    layer = _layer_for_path(path)
    if not layer:
        return []

    blocked_prefixes = _blocked_prefixes_for_layer(layer)
    if not blocked_prefixes:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors = []
    for lineno, module_name in _imported_modules(tree):
        if _is_blocked(module_name, blocked_prefixes):
            relative_path = path.relative_to(PROJECT_ROOT)
            errors.append(
                f"{relative_path}:{lineno}: {layer} layer must not import `{module_name}`"
            )
    return errors


def main() -> int:
    if not FEATURES_ROOT.exists():
        return 0

    errors = []
    errors.extend(check_removed_compat_paths())
    for path in FEATURES_ROOT.rglob("*.py"):
        errors.extend(check_file(path))

    if errors:
        print("Architecture check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Architecture check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
