# Ailey system package initializer

__all__ = [
    "ailey_personality",
    "ailey_memory",
    "creative_tools",
    "relationships",
    "journal",
]

# NOTE:
# Historically we auto-imported the large `tools*` modules here so their
# @register_tool decorators would execute at package import time. That makes
# importing `ailey_system` slow and can block (heavy network/FS/RPC during
# module init). To keep imports fast (very important for quick unit tests,
# CLI tools and smoke-tests) we lazily import those modules on attribute
# access instead. Callers that need the tools can either import them
# explicitly (from ailey_system import tools_code) or access attributes on
# the package (ailey_system.tools_code) which will import on demand.

_LAZY_TOOL_MODULES = (
    "tools",
    "tools_code",
    "tools_web",
    "tools_git",
    "tools_system",
)


def __getattr__(name: str):
    """Lazy import helpers for heavy submodules.

    This avoids executing module-level initialization in `tools_*` when
    importing the package itself. The first attribute access performs the
    import and caches the module on the package globals.
    """
    if name in _LAZY_TOOL_MODULES:
        import importlib

        mod = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Keep legacy behavior for `from ailey_system import *` but avoid importing
# heavy modules eagerly.
__all__ = __all__ + list(_LAZY_TOOL_MODULES)
