"""Discover model packages on disk and construct the selected engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from urdu_translator.errors import (
    ModelConfigError,
    ModelNotFoundError,
    TranslationFailedError,
    UnsupportedBackendError,
)
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.registry import get_backend, probe_backend

_RESERVED_KEYS = {
    "name",
    "backend",
    "source_language",
    "target_language",
    "default",
    "role",
}
_ROLES = {"literal", "contextual"}


@dataclass(frozen=True)
class EngineStatus:
    """What the window can say about the models directory before translating."""

    state: str
    short_label: str
    message: str
    model_name: str | None = None


def discover_packages(models_dir: Path) -> list[ModelPackage]:
    """Read every ``engine.json`` in an immediate subfolder of ``models_dir``."""
    root = Path(models_dir)
    if not root.exists():
        return []
    if not root.is_dir():
        raise ModelConfigError(f"The models path is not a folder: {root}")

    packages: list[ModelPackage] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        config_path = child / "engine.json"
        if config_path.is_file():
            packages.append(read_package(config_path))
    return packages


def read_package(config_path: Path) -> ModelPackage:
    """Parse one engine.json file into a :class:`ModelPackage`."""
    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except OSError as exc:
        raise ModelConfigError(f"Could not read {config_path}. {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelConfigError(f"{config_path.name} in {config_path.parent.name} is not valid JSON. {exc}") from exc

    if not isinstance(data, dict):
        raise ModelConfigError(f"{config_path} must contain a JSON object.")

    name = _required_text(data, "name", config_path)
    backend = _required_text(data, "backend", config_path)
    source_language = _optional_text(data, "source_language", "ur", config_path)
    target_language = _optional_text(data, "target_language", "en", config_path)
    is_default = _optional_bool(data, "default", config_path)
    role = _optional_role(data, config_path)
    options = {key: value for key, value in data.items() if key not in _RESERVED_KEYS}
    return ModelPackage(
        name=name,
        backend=backend,
        directory=config_path.parent,
        source_language=source_language,
        target_language=target_language,
        is_default=is_default,
        options=options,
        role=role,
    )


def select_package(packages: list[ModelPackage], models_dir: Path, role: str = "literal") -> ModelPackage:
    """Choose the package the application should load for one translation mode."""
    role = _check_role(role)
    gemma = [package for package in packages if package.backend == "gemma"]
    if gemma:
        packages = gemma
    packages = [package for package in packages if _package_matches_role(package, role)]
    if not packages:
        if role == "contextual":
            raise ModelNotFoundError(missing_contextual_message(models_dir))
        raise ModelNotFoundError(missing_model_message(models_dir))
    defaults = [package for package in packages if package.is_default]
    if len(defaults) == 1:
        return defaults[0]
    if len(defaults) > 1:
        names = ", ".join(package.name for package in defaults)
        raise ModelConfigError(
            "More than one model is marked as the default "
            f"({names}). Leave \"default\": true on only one engine.json file."
        )
    if len(packages) == 1:
        return packages[0]
    names = ", ".join(package.name for package in packages)
    raise ModelConfigError(
        f"Several model packages were found ({names}). "
        "Set \"default\": true in the engine.json of the model to use."
    )


def load_engine(models_dir: Path, role: str = "literal") -> TranslationEngine:
    """Load the local model for one mode. Raises when none can be used."""
    _ensure_backends_loaded()
    root = Path(models_dir)
    packages = discover_packages(root)
    if not packages:
        raise ModelNotFoundError(missing_model_message(root))
    package = select_package(packages, root, role)
    factory = get_backend(package.backend)
    if factory is None:
        raise UnsupportedBackendError(unsupported_backend_message(package))
    try:
        engine = factory(package)
    except TranslationFailedError:
        raise
    except Exception as exc:
        raise TranslationFailedError(f"The model “{package.name}” could not be started. {exc}") from exc
    if not isinstance(engine, TranslationEngine):
        raise TranslationFailedError(
            f"The backend “{package.backend}” did not return a translation engine."
        )
    return engine


def inspect_engine(models_dir: Path) -> EngineStatus:
    """Describe the models directory without loading model weights."""
    _ensure_backends_loaded()
    root = Path(models_dir)
    try:
        packages = discover_packages(root)
        if not packages:
            return EngineStatus("missing", "No model loaded", missing_model_message(root))
        package = select_package(packages, root, "literal")
    except ModelNotFoundError as exc:
        return EngineStatus("missing", "No model loaded", str(exc))
    except ModelConfigError as exc:
        return EngineStatus("invalid", "Check model setup", str(exc))

    if get_backend(package.backend) is None:
        return EngineStatus(
            "unsupported",
            "Backend not installed",
            unsupported_backend_message(package),
            package.name,
        )
    issue = probe_backend(package.backend, package)
    if issue:
        return EngineStatus("invalid", "Check model setup", issue, package.name)
    if package.backend == "gemma":
        detail = "No other translation engine is used."
    else:
        detail = _contextual_sentence(packages)
    return EngineStatus(
        "ready",
        package.name,
        (
            f"Ready to translate with {package.name}. Files are read from {package.directory}. "
            f"{detail}"
        ),
        package.name,
    )


def missing_contextual_message(models_dir: Path) -> str:
    return (
        "No contextual model was found in "
        f"{models_dir}. Add a model folder whose engine.json sets \"role\" to \"contextual\". "
        "The application does not download models."
    )


def missing_model_message(models_dir: Path) -> str:
    return (
        "No translation model was found in "
        f"{models_dir}. Add a model folder that contains an engine.json file. "
        "Models are read only from that folder."
    )


def unsupported_backend_message(package: ModelPackage) -> str:
    return (
        f"The model “{package.name}” in {package.directory} asks for the "
        f"“{package.backend}” backend, which is not installed in this version yet."
    )


def _ensure_backends_loaded() -> None:
    """Import the backends package so its registrations take effect."""
    import urdu_translator.translation.backends  # noqa: F401


def _required_text(data: dict[str, Any], key: str, config_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelConfigError(f"{config_path} must include a non-empty \"{key}\" string.")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str, default: str, config_path: Path) -> str:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ModelConfigError(f"\"{key}\" in {config_path} must be a non-empty string.")
    return value.strip()


def _contextual_sentence(packages: list[ModelPackage]) -> str:
    """Describe the contextual package without changing the literal status."""
    matches = [package for package in packages if package.role == "contextual"]
    if not matches:
        return (
            "No separate contextual model is installed. Contextual English uses the literal "
            "model, with the previous Urdu line when a reply is short."
        )
    defaults = [package for package in matches if package.is_default]
    if len(matches) > 1 and len(defaults) != 1:
        return "More than one contextual model is configured. Mark one engine.json with \"default\": true."
    package = defaults[0] if defaults else matches[0]
    if get_backend(package.backend) is None:
        return (
            f"The contextual model “{package.name}” asks for the “{package.backend}” backend, "
            "which is not installed."
        )
    issue = probe_backend(package.backend, package)
    if issue:
        return (
            f"The contextual model “{package.name}” is not ready. {issue} "
            "Contextual English will use the literal model until that model is ready."
        )
    return f"Contextual English uses {package.name}."


def _package_matches_role(package: ModelPackage, role: str) -> bool:
    if role == "contextual":
        return package.role == "contextual"
    return package.role != "contextual"


def _check_role(role: str) -> str:
    if role not in _ROLES:
        raise ModelConfigError(f"Unknown translation mode \"{role}\". Use literal or contextual.")
    return role


def _optional_role(data: dict[str, Any], config_path: Path) -> str:
    if "role" not in data:
        return "literal"
    value = data["role"]
    if not isinstance(value, str) or value.strip().lower() not in _ROLES:
        raise ModelConfigError(f"\"role\" in {config_path} must be \"literal\" or \"contextual\".")
    return value.strip().lower()


def _optional_bool(data: dict[str, Any], key: str, config_path: Path) -> bool:
    if key not in data:
        return False
    value = data[key]
    if not isinstance(value, bool):
        raise ModelConfigError(f"\"{key}\" in {config_path} must be true or false.")
    return value
