import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURES_ROOT = PROJECT_ROOT / "Echo-backend" / "features"
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
REMOVED_COMPAT_PATHS = (
    BACKEND_ROOT / "services",
    BACKEND_ROOT / "api",
    BACKEND_ROOT / "schemas",
    BACKEND_ROOT / "repositories",
    BACKEND_ROOT / "config.py",
    BACKEND_ROOT / "llm_client.py",
    BACKEND_ROOT / "db" / "sqlite_connection.py",
    BACKEND_ROOT / "db" / "sqlite_schema.py",
    BACKEND_ROOT / "db" / "connection.py",
    BACKEND_ROOT / "db" / "schema.py",
    BACKEND_ROOT / "db" / "migrations",
    BACKEND_ROOT / "features" / "admin",
    BACKEND_ROOT / "features" / "character_animation",
    BACKEND_ROOT / "features" / "chat" / "infrastructure" / "prompt_renderer.py",
    PROJECT_ROOT / "app" / "lib" / "features" / "home",
    PROJECT_ROOT / "app" / "lib" / "features" / "call",
    BACKEND_ROOT / "features" / "auth" / "infrastructure" / "sqlite_repositories.py",
    BACKEND_ROOT / "features" / "chat" / "infrastructure" / "sqlite_repositories.py",
    BACKEND_ROOT / "features" / "memory" / "infrastructure" / "sqlite_repositories.py",
    BACKEND_ROOT / "features" / "auth" / "infrastructure" / "repository_provider.py",
    BACKEND_ROOT / "features" / "chat" / "infrastructure" / "repository_provider.py",
    BACKEND_ROOT / "features" / "memory" / "infrastructure" / "repository_provider.py",
    PROJECT_ROOT / "scripts" / "migrate_sqlite_to_postgres.py",
    PROJECT_ROOT / "deploy" / "funasr",
    PROJECT_ROOT / "deploy" / "melotts",
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
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in blocked_prefixes
    )


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
            errors.append(
                f"{path.relative_to(PROJECT_ROOT)}: removed compatibility file must not exist"
            )
        elif path.is_dir() and any(
            candidate.is_file() and "__pycache__" not in candidate.parts
            for candidate in path.rglob("*")
        ):
            errors.append(
                f"{path.relative_to(PROJECT_ROOT)}: removed compatibility directory must be empty"
            )
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
    if layer == "interface":
        errors.extend(check_implemented_routes(tree, str(path.relative_to(PROJECT_ROOT))))
    return errors


def check_implemented_routes(tree: ast.AST, source: str) -> list[str]:
    """Reject executable API stubs without mistaking Protocols for missing features."""
    errors = []
    verbs = {"get", "post", "put", "patch", "delete", "websocket", "api_route"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routed = any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in verbs
            for decorator in node.decorator_list
        )
        if not routed:
            continue
        statements = [
            item
            for item in node.body
            if not (
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            )
        ]
        empty = not statements or all(
            isinstance(item, ast.Pass)
            or (
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant)
                and item.value.value is Ellipsis
            )
            for item in statements
        )
        unimplemented = any(
            isinstance(item, ast.Raise)
            and (
                isinstance(item.exc, ast.Name)
                and item.exc.id == "NotImplementedError"
                or isinstance(item.exc, ast.Call)
                and isinstance(item.exc.func, ast.Name)
                and item.exc.func.id == "NotImplementedError"
            )
            for item in ast.walk(node)
        )
        if empty or unimplemented:
            errors.append(f"{source}:{node.lineno}: route `{node.name}` must be implemented")
    return errors


def check_shared_prompt_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    blocked = ("features", "db", "providers", "fastapi", "pydantic", "httpx")
    return [
        f"{path.relative_to(PROJECT_ROOT)}:{line}: shared prompting must not import `{module}`"
        for line, module in _imported_modules(tree)
        if _is_blocked(module, blocked)
    ]


def check_prompt_assets(renderer: Path, asset_root: Path) -> list[str]:
    """The four existing external rules must be loaded, nonempty runtime assets."""
    tree = ast.parse(renderer.read_text(encoding="utf-8"), filename=str(renderer))
    loaded = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_load_rule"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    errors = []
    for name in loaded:
        path = asset_root / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"{path}: runtime prompt rule must exist and contain content")
    for path in asset_root.glob("*.md"):
        if path.name != "README.md" and path.name not in loaded:
            errors.append(f"{path}: prompt rule has no runtime consumer")
    return errors


def main() -> int:
    if not FEATURES_ROOT.exists():
        return 0

    errors = []
    errors.extend(check_removed_compat_paths())
    for path in FEATURES_ROOT.rglob("*.py"):
        errors.extend(check_file(path))
    for feature in FEATURES_ROOT.iterdir():
        if (
            feature.is_dir()
            and feature.name != "__pycache__"
            and not any(path.name != "__init__.py" for path in feature.rglob("*.py"))
        ):
            errors.append(f"{feature.relative_to(PROJECT_ROOT)}: empty feature must not exist")
    for path in (BACKEND_ROOT / "shared" / "prompting").rglob("*.py"):
        errors.extend(check_shared_prompt_file(path))
    errors.extend(
        check_prompt_assets(
            BACKEND_ROOT / "shared" / "prompting" / "renderer.py",
            BACKEND_ROOT / "prompts" / "rules",
        )
    )

    if errors:
        print("Architecture check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Architecture check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
