"""Translation engine interface.

The window talks to :class:`TranslationEngine` and never names a model.
A future offline backend registers a factory under a short key; the models
folder selects which package is loaded.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from urdu_translator.translation.package import ModelPackage


class TranslationEngine(ABC):
    """Translates batches of plain text on a background thread."""

    def __init__(self, package: ModelPackage) -> None:
        self.package = package

    @property
    def name(self) -> str:
        """Human-readable name taken from the model package."""
        return self.package.name

    @abstractmethod
    def translate_batch(self, texts: list[str]) -> list[str]:
        """Return one translation for each input string, in the same order.

        Implementations must not reach the network. Empty input strings are
        not sent by the document service.
        """
