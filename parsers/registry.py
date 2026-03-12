"""
Parser registry — maps (institution_key, file_format) to a concrete parser class.

Usage
-----
Register at module load time (inside each institution parser file):

    from parsers.registry import ParserRegistry

    @ParserRegistry.register("fidelity", formats=["pdf", "csv"])
    class FidelityParser(BaseParser):
        ...

Retrieve at runtime:

    parser_cls = ParserRegistry.get_parser("fidelity", "pdf")
    result = parser_cls().parse(path)

If no institution-specific parser matches, the generic fallback is returned.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from parsers.base.parser_interface import BaseParser

logger = logging.getLogger(__name__)

_ParserT = TypeVar("_ParserT", bound="BaseParser")

# Registry structure:
#   { "institution_key": { "pdf": ParserClass, "csv": ParserClass, ... } }
_REGISTRY: dict[str, dict[str, type["BaseParser"]]] = {}

# Generic / fallback parsers keyed by format
_GENERIC_REGISTRY: dict[str, type["BaseParser"]] = {}


class ParserRegistry:
    @staticmethod
    def register(
        institution_key: str,
        formats: list[str],
    ):
        """Class decorator that registers a parser for the given institution and formats."""

        def decorator(cls: type[_ParserT]) -> type[_ParserT]:
            _REGISTRY.setdefault(institution_key, {})
            for fmt in formats:
                if fmt in _REGISTRY[institution_key]:
                    existing = _REGISTRY[institution_key][fmt]
                    logger.warning(
                        "Parser registry conflict: %s.%s overwriting %s for format %s",
                        institution_key,
                        cls.__name__,
                        existing.__name__,
                        fmt,
                    )
                _REGISTRY[institution_key][fmt] = cls
            return cls

        return decorator

    @staticmethod
    def register_generic(formats: list[str]):
        """Class decorator for generic (non-institution-specific) parsers."""

        def decorator(cls: type[_ParserT]) -> type[_ParserT]:
            for fmt in formats:
                _GENERIC_REGISTRY[fmt] = cls
            return cls

        return decorator

    @classmethod
    def get_parser(
        cls,
        institution_key: str | None,
        file_format: str,
    ) -> type["BaseParser"] | None:
        """
        Return the best parser class for this institution and format combination.
        Falls back to a generic parser if no institution-specific one is registered.
        Returns None if no suitable parser exists — the pipeline should mark the
        import session as NEEDS_REVIEW.
        """
        normalized_fmt = file_format.lower().lstrip(".")
        if institution_key:
            institution_parsers = _REGISTRY.get(institution_key, {})
            if normalized_fmt in institution_parsers:
                return institution_parsers[normalized_fmt]

        # Generic fallback
        if normalized_fmt in _GENERIC_REGISTRY:
            logger.info(
                "No institution parser for %s/%s — using generic",
                institution_key,
                normalized_fmt,
            )
            return _GENERIC_REGISTRY[normalized_fmt]

        logger.warning(
            "No parser available for institution=%s format=%s",
            institution_key,
            normalized_fmt,
        )
        return None

    @classmethod
    def list_registered(cls) -> dict[str, list[str]]:
        """Return a summary dict of all registered parsers for diagnostics."""
        result: dict[str, list[str]] = {}
        for institution_key, formats in _REGISTRY.items():
            result[institution_key] = list(formats.keys())
        if _GENERIC_REGISTRY:
            result["__generic__"] = list(_GENERIC_REGISTRY.keys())
        return result

    @classmethod
    def load_all_parsers(cls) -> None:
        """
        Import all institution parser modules so their @register decorators run.
        Call this once at application startup or at the start of the Celery worker.
        """
        import importlib
        import pkgutil
        import parsers.institutions as _institutions_pkg
        import parsers.generic as _generic_pkg

        for _package in [_institutions_pkg, _generic_pkg]:
            for _finder, name, _is_pkg in pkgutil.walk_packages(
                path=_package.__path__,
                prefix=_package.__name__ + ".",
            ):
                try:
                    importlib.import_module(name)
                    logger.debug("Loaded parser module: %s", name)
                except Exception as exc:
                    logger.error("Failed to load parser module %s: %s", name, exc)
