from collections.abc import Callable
from typing import Any

ProviderFactory = Callable[[], Any]

_provider_factories: dict[str, ProviderFactory] = {}
_provider_instances: dict[str, Any] = {}


def register_provider_factory(provider_name: str, factory: ProviderFactory) -> None:
    clean_provider_name = provider_name.strip()
    if not clean_provider_name:
        raise ValueError("Provider name cannot be empty")

    _provider_factories[clean_provider_name] = factory
    _provider_instances.pop(clean_provider_name, None)


def get_provider(provider_name: str, default_factory: ProviderFactory) -> Any:
    clean_provider_name = provider_name.strip()
    if not clean_provider_name:
        raise ValueError("Provider name cannot be empty")

    if clean_provider_name not in _provider_instances:
        factory = _provider_factories.get(clean_provider_name, default_factory)
        _provider_instances[clean_provider_name] = factory()
    return _provider_instances[clean_provider_name]


def reset_provider_registry_for_tests() -> None:
    _provider_factories.clear()
    _provider_instances.clear()
