import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("URDU_TRANSLATOR_DATA", tempfile.mkdtemp(prefix="urdu-translator-tests-"))
