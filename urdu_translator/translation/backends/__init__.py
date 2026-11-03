"""Offline translation backends.

Importing this package registers backends. The window does not choose a model;
``engine.json`` in the models directory does.
"""

from urdu_translator.translation.backends.gemma import register as register_gemma
from urdu_translator.translation.backends.indictrans2 import register as register_indictrans
from urdu_translator.translation.backends.marian import register

register()
register_indictrans()
register_gemma()
