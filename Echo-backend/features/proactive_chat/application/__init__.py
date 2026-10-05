"""Application services for proactive chat.

Keep this package initializer free of eager imports so chat reply generation
can import reminder parsing without loading the proactive worker back into the
chat module during application startup.
"""
