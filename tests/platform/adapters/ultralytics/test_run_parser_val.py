from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.adapters.ultralytics.run_parser import UltralyticsRunParser


class TestParseValPerClassMetrics:
    def test_parses_valid_json(self):
        parser = UltralyticsRunParser()
        data = {
            "ap_per_class": {"0": 0.852, "1": 0.731, "2": 0.943},
            "class_names": ["cat", "dog", "bird"],
            "mAP50": 0.842,
            "mAP50_95": 0.651,
            "precision": 0.88,
            "recall": 0.79,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "per_class_metrics.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = parser.parse_val_per_class_metrics(str(path))
            assert result is not None
            assert result["mAP50"] == 0.842
            assert result["ap_per_class"]["0"] == 0.852
            assert len(result["class_names"]) == 3

    def test_returns_none_for_missing_file(self):
        parser = UltralyticsRunParser()
        result = parser.parse_val_per_class_metrics("/nonexistent/path.json")
        assert result is None

    def test_returns_none_for_invalid_json(self):
        parser = UltralyticsRunParser()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            result = parser.parse_val_per_class_metrics(str(path))
            assert result is None


class TestParseValConfusionMatrix:
    def test_loads_npy_file(self):
        parser = UltralyticsRunParser()
        matrix = np.array([[45, 2, 1], [3, 38, 0], [0, 1, 50]], dtype=np.int32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "confusion_matrix.npy"
            np.save(str(path), matrix)
            result = parser.parse_val_confusion_matrix(str(path))
            assert result is not None
            assert result.shape == (3, 3)
            assert result[0, 0] == 45

    def test_returns_none_for_missing_file(self):
        parser = UltralyticsRunParser()
        result = parser.parse_val_confusion_matrix("/nonexistent/path.npy")
        assert result is None
