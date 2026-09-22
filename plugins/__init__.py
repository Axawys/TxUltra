"""Drop-in plugin directory.

Add a new tool by placing a module here that defines a subclass of
``core.plugin_base.Plugin`` and exposes it as module-level ``PLUGIN`` (an
instance) or as any ``Plugin`` subclass. The loader discovers it at startup;
no core changes required. See ``_example.py`` for the smallest possible plugin.
"""
