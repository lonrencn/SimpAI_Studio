import os
import sys

try:
    from comfy_env import register_nodes
    NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = register_nodes()
except ImportError:
    _dir = os.path.dirname(os.path.abspath(__file__))
    _inserted = False
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
        _inserted = True
    try:
        from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    except Exception:
        NODE_CLASS_MAPPINGS = {}
        NODE_DISPLAY_NAME_MAPPINGS = {}
    finally:
        if _inserted:
            sys.path.remove(_dir)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
