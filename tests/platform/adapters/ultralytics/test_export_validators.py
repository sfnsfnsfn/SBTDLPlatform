from __future__ import annotations

from anylabeling.platform.adapters.ultralytics.export_validators import (
    SUPPORTED_EXPORT_FORMATS,
    get_export_validator,
    validate_export_environment,
)


class TestSupportedFormats:
    def test_onnx_is_supported(self):
        assert "onnx" in SUPPORTED_EXPORT_FORMATS

    def test_engine_is_supported(self):
        assert "engine" in SUPPORTED_EXPORT_FORMATS

    def test_coreml_is_supported(self):
        assert "coreml" in SUPPORTED_EXPORT_FORMATS

    def test_torchscript_is_supported(self):
        assert "torchscript" in SUPPORTED_EXPORT_FORMATS

    def test_at_least_15_formats(self):
        assert len(SUPPORTED_EXPORT_FORMATS) >= 15

    def test_all_formats_have_validator(self):
        for fmt in SUPPORTED_EXPORT_FORMATS:
            validator = get_export_validator(fmt)
            assert callable(validator), f"No validator for: {fmt}"

    def test_unknown_format_returns_noop(self):
        validator = get_export_validator("unknown_format")
        result = validator()
        assert result == []


class TestValidateExportEnvironment:
    def test_torchscript_always_passes(self):
        missing = validate_export_environment("torchscript")
        assert missing == []

    def test_onnx_returns_list(self):
        missing = validate_export_environment("onnx")
        assert isinstance(missing, list)
