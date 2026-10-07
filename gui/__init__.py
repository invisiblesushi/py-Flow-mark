"""FlowMark GUI package. Prefer: python gui.py  or  python -m gui"""

__all__ = ["FlowMarkApp", "main"]


def __getattr__(name):
    if name in ("FlowMarkApp", "main"):
        from .app import FlowMarkApp, main
        return FlowMarkApp if name == "FlowMarkApp" else main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
