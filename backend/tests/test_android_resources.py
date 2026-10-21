"""Resource migration preserves account data and the shared model bundle."""
from pathlib import Path

import pytest

from backend.app.android.resources import LEGACY_RESOURCES, MODELS, prepare_resources


def test_shared_model_validation_precedes_cache_cleanup(tmp_path):
    legacy = tmp_path / "data/console/1/assets/common_old.onnx"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"previous model")
    with pytest.raises(RuntimeError):
        prepare_resources(tmp_path / "data", tmp_path / "models")
    assert legacy.read_bytes() == b"previous model"


def test_cleanup_removes_only_generated_account_resources(tmp_path):
    models = tmp_path / "bundle/models"
    models.mkdir(parents=True)
    for name in MODELS:
        (models / name).write_bytes(b"shared model")
    data = tmp_path / "data"
    for account in ("1", "2", "notes"):
        assets = data / "console" / account / "assets"
        assets.mkdir(parents=True)
        for name in LEGACY_RESOURCES:
            (assets / name).write_bytes(b"old resource")
        (assets / "cmap.json").write_text("{}")
        (assets.parent / "config.yaml").write_text("account state")
    prepare_resources(data, models)
    prepare_resources(data, models)
    for account in ("1", "2"):
        assets = data / "console" / account / "assets"
        assert all(not (assets / name).exists() for name in LEGACY_RESOURCES)
        assert (assets / "cmap.json").read_text() == "{}"
        assert (assets.parent / "config.yaml").read_text() == "account state"
    assert all((data / "console/notes/assets" / name).exists() for name in LEGACY_RESOURCES)
    assert all((models / name).read_bytes() == b"shared model" for name in MODELS)
