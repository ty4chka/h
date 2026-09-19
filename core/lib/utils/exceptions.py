# core/lib/utils/exceptions.py
class CommandConflictError(Exception):
    """Команда с таким именем уже зарегистрирована."""
