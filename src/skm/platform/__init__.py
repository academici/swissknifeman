"""Infrastructure primitives below the modules: configuration, filesystem, processes, schemas and logging.

Platform code may import ``kernel`` but never ``modules``, ``application_bus`` or ``bootstrap``. The
``system_*`` files are the only readers of the wall clock, entropy and id generation.
"""
