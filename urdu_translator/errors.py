"""Errors that the desktop interface can show directly to the user."""


class AppError(Exception):
    """An expected failure with a message safe to display."""


class TranslationError(AppError):
    """The translation pipeline could not complete."""


class ModelNotFoundError(TranslationError):
    """The models directory has no usable model package."""


class ModelConfigError(TranslationError):
    """A model package is present, but its engine.json file is not usable."""


class UnsupportedBackendError(TranslationError):
    """The model names a backend that this build does not provide."""


class TranslationFailedError(TranslationError):
    """A loaded engine failed while translating."""


class TranslationCancelled(TranslationError):
    """The user left the translation before it finished."""


class DocumentError(AppError):
    """A text or Word file could not be read or written."""
