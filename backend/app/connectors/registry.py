"""Config-driven connector registry & factory.

New connector types register with @register_connector("type") - no core changes
required to add engines.
"""
from __future__ import annotations

from typing import Callable, Type

from app.connectors.base import IAnalyticsConnector
from app.core.config import get_settings
from app.core.exceptions import ConnectorError, NotFound

_CONNECTOR_TYPES: dict[str, Type[IAnalyticsConnector]] = {}
_instances: dict[str, IAnalyticsConnector] = {}


def register_connector(type_name: str) -> Callable:
    def decorator(cls: Type[IAnalyticsConnector]):
        _CONNECTOR_TYPES[type_name] = cls
        return cls
    return decorator


def available_types() -> list[str]:
    return sorted(_CONNECTOR_TYPES)


def list_connector_ids() -> list[str]:
    return sorted(get_settings().section("connectors.definitions"))


def default_connector_id() -> str:
    return get_settings().get("connectors.default", "hive")


def get_connector(connector_id: str | None = None) -> IAnalyticsConnector:
    settings = get_settings()
    cid = connector_id or default_connector_id()
    if cid in _instances:
        return _instances[cid]
    definitions = settings.section("connectors.definitions")
    if cid not in definitions:
        raise NotFound(f"Connector '{cid}' is not configured")
    config = definitions[cid]
    type_name = config.get("type")
    cls = _CONNECTOR_TYPES.get(type_name)
    if cls is None:
        raise ConnectorError(
            f"Connector type '{type_name}' is not installed. Available: {available_types()}"
        )
    instance = cls(cid, config)
    _instances[cid] = instance
    return instance


async def close_all() -> None:
    for instance in _instances.values():
        await instance.close()
    _instances.clear()


def _load_builtin_connectors() -> None:
    """Import built-in connector modules so their decorators run."""
    from app.connectors.hive import connector as _hive  # noqa: F401


_load_builtin_connectors()
