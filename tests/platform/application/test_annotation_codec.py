"""Tests for AnnotationCodec protocol and XLabelCodec implementation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from anylabeling.platform.application.annotation_service import XLabelCodec
from anylabeling.platform.application.ports import AnnotationCodec
from anylabeling.platform.domain.annotation import (
    AnnotationDocument,
    AnnotationObject,
)

# ---------------------------------------------------------------------------
# Path to shared test fixtures
# ---------------------------------------------------------------------------
_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "e2e" / "platform" / "fixtures" / "annotations"

HBB_SAMPLE = _FIXTURES_DIR / "hbb_sample.json"
OBB_SAMPLE = _FIXTURES_DIR / "obb_sample.json"
POLYGON_SAMPLE = _FIXTURES_DIR / "polygon_sample.json"
POSE_SAMPLE = _FIXTURES_DIR / "pose_sample.json"
CLASSIFY_SAMPLE = _FIXTURES_DIR / "classify_sample.json"
EMPTY_BACKGROUND_SAMPLE = _FIXTURES_DIR / "empty_background.json"
CI_LARGE_SAMPLE = _FIXTURES_DIR / "ci_large_sample.json"

# Image dimensions used in the fixtures
IMG_W, IMG_H = 640, 480


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _make_doc(**kwargs) -> AnnotationDocument:
    defaults = {
        "asset_id": "test.png",
        "image_width": 640,
        "image_height": 480,
        "objects": [],
        "image_labels": {},
    }
    defaults.update(kwargs)
    return AnnotationDocument(**defaults)


# ---------------------------------------------------------------------------
# Protocol compliance check
# ---------------------------------------------------------------------------
class TestAnnotationCodecProtocol(unittest.TestCase):
    """Verify that XLabelCodec satisfies the AnnotationCodec Protocol."""

    def test_xlabel_codec_is_annotation_codec(self):
        codec = XLabelCodec()
        self.assertIsInstance(codec, AnnotationCodec)

    def test_xlabel_codec_has_required_methods(self):
        codec = XLabelCodec()
        self.assertTrue(callable(codec.load_annotations))
        self.assertTrue(callable(codec.save_annotations))
        self.assertTrue(callable(codec.validate_annotations))


# ---------------------------------------------------------------------------
# Load tests — shape type mapping
# ---------------------------------------------------------------------------
class TestLoadRectangleShapes(unittest.TestCase):
    """Load X-AnyLabeling JSON with rectangle shapes -> AnnotationDocument with bbox_xyxy."""

    def test_load_hbb_sample(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(HBB_SAMPLE), IMG_W, IMG_H)

        self.assertEqual(doc.asset_id, "hbb_sample.png")
        self.assertEqual(doc.image_width, IMG_W)
        self.assertEqual(doc.image_height, IMG_H)
        self.assertEqual(len(doc.objects), 3)

        for obj in doc.objects:
            self.assertEqual(obj.geometry_type, "bbox_xyxy")
            self.assertIsInstance(obj.geometry, tuple)
            self.assertEqual(len(obj.geometry), 4)
            x1, y1, x2, y2 = obj.geometry
            self.assertLess(x1, x2)
            self.assertLess(y1, y2)
            self.assertIn(obj.attributes["label"], ["defect"])


class TestLoadRotationShapes(unittest.TestCase):
    """Load X-AnyLabeling JSON with rotation shapes -> AnnotationDocument with obb_polygon."""

    def test_load_obb_sample(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(OBB_SAMPLE), IMG_W, IMG_H)

        self.assertEqual(len(doc.objects), 2)
        for obj in doc.objects:
            self.assertEqual(obj.geometry_type, "obb_polygon")
            self.assertIsInstance(obj.geometry, list)
            self.assertEqual(len(obj.geometry), 4)


class TestLoadPolygonShapes(unittest.TestCase):
    """Load X-AnyLabeling JSON with polygon shapes -> AnnotationDocument with polygon."""

    def test_load_polygon_sample(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(POLYGON_SAMPLE), IMG_W, IMG_H)

        self.assertEqual(len(doc.objects), 2)
        for obj in doc.objects:
            self.assertEqual(obj.geometry_type, "polygon")
            self.assertIsInstance(obj.geometry, list)
            self.assertGreaterEqual(len(obj.geometry), 3)


class TestLoadPointShapes(unittest.TestCase):
    """Load X-AnyLabeling JSON with point shapes -> AnnotationDocument with keypoints."""

    def test_load_pose_sample(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(POSE_SAMPLE), IMG_W, IMG_H)

        # pose_sample has 2 shapes, each containing 13 keypoints
        # Each shape maps to one AnnotationObject with geometry_type="keypoints"
        self.assertEqual(len(doc.objects), 2)
        for obj in doc.objects:
            self.assertEqual(obj.geometry_type, "keypoints")
            self.assertIsInstance(obj.geometry, list)
            # Each shape has 13 keypoints
            self.assertEqual(len(obj.geometry), 13)
            # Each keypoint should have (x, y, visibility=2)
            for kp in obj.geometry:
                self.assertEqual(len(kp), 3)
                self.assertEqual(kp[2], 2)  # default visibility


class TestLoadClassifyShapes(unittest.TestCase):
    """Load X-AnyLabeling JSON with only flags -> AnnotationDocument (classification)."""

    def test_load_classify_sample(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(CLASSIFY_SAMPLE), IMG_W, IMG_H)

        self.assertEqual(len(doc.objects), 0)
        self.assertTrue(doc.image_labels)
        self.assertIn("defect_free", doc.image_labels)
        self.assertTrue(doc.image_labels["defect_free"])


class TestLoadEmptyBackground(unittest.TestCase):
    """Empty annotation file -> empty AnnotationDocument (not error)."""

    def test_load_empty_background(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(
            str(EMPTY_BACKGROUND_SAMPLE), IMG_W, IMG_H
        )
        self.assertEqual(len(doc.objects), 0)
        self.assertTrue(doc.image_labels)  # has flags
        self.assertIn("empty", doc.image_labels)


class TestUnknownShapeType(unittest.TestCase):
    """Unknown shape type -> validation warning (not exception)."""

    def test_unknown_shape_type(self):
        codec = XLabelCodec()
        # We construct a synthetic JSON with an unknown shape type
        data = {
            "version": "4.0.0-beta.7",
            "flags": {},
            "shapes": [
                {
                    "label": "test",
                    "points": [[10, 20], [30, 40]],
                    "shape_type": "unknown_fancy_type",
                    "flags": {},
                    "description": "",
                    "attributes": {},
                }
            ],
            "imagePath": "test.png",
            "imageHeight": 480,
            "imageWidth": 640,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            doc = codec.load_annotations(tmp_path, 640, 480)
            # Should not raise; unknown type mapped to polygon
            self.assertEqual(len(doc.objects), 1)
            self.assertEqual(doc.objects[0].geometry_type, "polygon")
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Save tests
# ---------------------------------------------------------------------------
class TestSaveAnnotations(unittest.TestCase):
    """Save AnnotationDocument -> valid X-AnyLabeling JSON."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_save_rectangle(self):
        codec = XLabelCodec(classes=["defect"])
        doc = _make_doc(
            asset_id="test_rect.png",
            image_width=640,
            image_height=480,
            objects=[
                AnnotationObject(
                    id="obj1",
                    label_id=0,
                    geometry_type="bbox_xyxy",
                    geometry=(50.0, 50.0, 150.0, 120.0),
                    attributes={"label": "defect"},
                )
            ],
        )
        output = Path(self.tmp_dir) / "test_rect.json"
        codec.save_annotations(doc, str(output))

        self.assertTrue(output.exists())
        with open(output, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["imageWidth"], 640)
        self.assertEqual(saved["imageHeight"], 480)
        self.assertEqual(len(saved["shapes"]), 1)
        shape = saved["shapes"][0]
        self.assertEqual(shape["shape_type"], "rectangle")
        self.assertEqual(shape["label"], "defect")
        # Should have 4 points forming a rectangle
        self.assertEqual(len(shape["points"]), 4)

    def test_save_polygon(self):
        codec = XLabelCodec(classes=["defect"])
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="obj1",
                    label_id=0,
                    geometry_type="polygon",
                    geometry=[(10.0, 10.0), (100.0, 10.0), (100.0, 100.0)],
                    attributes={"label": "defect"},
                )
            ],
        )
        output = Path(self.tmp_dir) / "test_poly.json"
        codec.save_annotations(doc, str(output))

        with open(output, "r", encoding="utf-8") as f:
            saved = json.load(f)

        shape = saved["shapes"][0]
        self.assertEqual(shape["shape_type"], "polygon")
        self.assertEqual(len(shape["points"]), 3)

    def test_save_obb(self):
        codec = XLabelCodec(classes=["rotated"])
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="obj1",
                    label_id=0,
                    geometry_type="obb_polygon",
                    geometry=[
                        (83.0, 146.0),
                        (187.0, 206.0),
                        (217.0, 154.0),
                        (113.0, 94.0),
                    ],
                    attributes={"label": "rotated"},
                )
            ],
        )
        output = Path(self.tmp_dir) / "test_obb.json"
        codec.save_annotations(doc, str(output))

        with open(output, "r", encoding="utf-8") as f:
            saved = json.load(f)

        shape = saved["shapes"][0]
        self.assertEqual(shape["shape_type"], "rotation")
        self.assertEqual(len(shape["points"]), 4)

    def test_save_keypoints(self):
        codec = XLabelCodec(classes=["person"])
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="obj1",
                    label_id=0,
                    geometry_type="keypoints",
                    geometry=[(150.0, 80.0, 2)],
                    attributes={"label": "person"},
                )
            ],
        )
        output = Path(self.tmp_dir) / "test_kpts.json"
        codec.save_annotations(doc, str(output))

        with open(output, "r", encoding="utf-8") as f:
            saved = json.load(f)

        shape = saved["shapes"][0]
        self.assertEqual(shape["shape_type"], "point")
        self.assertEqual(shape["points"], [[150.0, 80.0]])

    def test_save_classification(self):
        codec = XLabelCodec()
        doc = _make_doc(
            image_labels={"defect_free": True, "good_lighting": False},
        )
        output = Path(self.tmp_dir) / "test_classify.json"
        codec.save_annotations(doc, str(output))

        with open(output, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertIn("defect_free", saved["flags"])
        self.assertTrue(saved["flags"]["defect_free"])


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------
class TestRoundTrip(unittest.TestCase):
    """load -> save -> load produces identical AnnotationDocument."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def _docs_equivalent(self, a: AnnotationDocument, b: AnnotationDocument) -> bool:
        """Compare two AnnotationDocuments for structural equivalence."""
        if a.asset_id != b.asset_id:
            return False
        if a.image_width != b.image_width:
            return False
        if a.image_height != b.image_height:
            return False
        if len(a.objects) != len(b.objects):
            return False
        if a.image_labels != b.image_labels:
            return False

        for oa, ob in zip(a.objects, b.objects):
            if oa.label_id != ob.label_id:
                return False
            if oa.geometry_type != ob.geometry_type:
                return False
            if oa.attributes.get("label") != ob.attributes.get("label"):
                return False
            # Compare geometry with tolerance for float precision
            if not self._geometries_equal(oa.geometry, ob.geometry, oa.geometry_type):
                return False
        return True

    def _geometries_equal(self, ga, gb, geom_type) -> bool:
        if geom_type == "bbox_xyxy":
            return all(abs(float(a) - float(b)) < 1e-4 for a, b in zip(ga, gb))
        if geom_type in ("polygon", "obb_polygon"):
            if len(ga) != len(gb):
                return False
            for pa, pb in zip(ga, gb):
                if abs(float(pa[0]) - float(pb[0])) >= 1e-4:
                    return False
                if abs(float(pa[1]) - float(pb[1])) >= 1e-4:
                    return False
            return True
        if geom_type == "keypoints":
            if len(ga) != len(gb):
                return False
            for ka, kb in zip(ga, gb):
                if (
                    abs(float(ka[0]) - float(kb[0])) >= 1e-4
                    or abs(float(ka[1]) - float(kb[1])) >= 1e-4
                ):
                    return False
            return True
        return False

    def test_round_trip_hbb(self):
        codec = XLabelCodec()
        doc1 = codec.load_annotations(str(HBB_SAMPLE), IMG_W, IMG_H)

        mid_path = Path(self.tmp_dir) / "roundtrip_hbb.json"
        codec.save_annotations(doc1, str(mid_path))

        doc2 = codec.load_annotations(str(mid_path), IMG_W, IMG_H)
        self.assertTrue(
            self._docs_equivalent(doc1, doc2),
            "Round-trip AnnotationDocuments differ",
        )

    def test_round_trip_obb(self):
        codec = XLabelCodec()
        doc1 = codec.load_annotations(str(OBB_SAMPLE), IMG_W, IMG_H)

        mid_path = Path(self.tmp_dir) / "roundtrip_obb.json"
        codec.save_annotations(doc1, str(mid_path))

        doc2 = codec.load_annotations(str(mid_path), IMG_W, IMG_H)
        self.assertTrue(
            self._docs_equivalent(doc1, doc2),
            "Round-trip AnnotationDocuments differ",
        )

    def test_round_trip_polygon(self):
        codec = XLabelCodec()
        doc1 = codec.load_annotations(str(POLYGON_SAMPLE), IMG_W, IMG_H)

        mid_path = Path(self.tmp_dir) / "roundtrip_polygon.json"
        codec.save_annotations(doc1, str(mid_path))

        doc2 = codec.load_annotations(str(mid_path), IMG_W, IMG_H)
        self.assertTrue(
            self._docs_equivalent(doc1, doc2),
            "Round-trip AnnotationDocuments differ",
        )


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------
class TestValidateAnnotations(unittest.TestCase):
    """Validate catches: out-of-bounds, invalid label_id, self-intersecting polygon."""

    def test_valid_document_no_issues(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(HBB_SAMPLE), IMG_W, IMG_H)
        issues = codec.validate_annotations(doc)
        self.assertEqual(issues, [])

    def test_out_of_bounds_coordinates(self):
        codec = XLabelCodec()
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="bad1",
                    label_id=0,
                    geometry_type="bbox_xyxy",
                    geometry=(-10.0, -10.0, 200.0, 200.0),
                    attributes={"label": "defect"},
                )
            ],
        )
        issues = codec.validate_annotations(doc)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any("outside" in i for i in issues))

    def test_invalid_label_id(self):
        codec = XLabelCodec()
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="bad2",
                    label_id=-1,
                    geometry_type="bbox_xyxy",
                    geometry=(50.0, 50.0, 100.0, 100.0),
                    attributes={"label": "defect"},
                )
            ],
        )
        issues = codec.validate_annotations(doc)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any("label_id" in i for i in issues))

    def test_self_intersecting_polygon(self):
        codec = XLabelCodec()
        # Bow-tie shape: self-intersecting polygon
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="bowtie",
                    label_id=0,
                    geometry_type="polygon",
                    geometry=[(0, 0), (100, 100), (0, 100), (100, 0)],
                    attributes={"label": "defect"},
                )
            ],
        )
        issues = codec.validate_annotations(doc)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(
            any("self-intersecting" in i for i in issues),
            f"Expected self-intersecting warning, got: {issues}",
        )

    def test_non_finite_coordinates(self):
        codec = XLabelCodec()
        doc = _make_doc(
            objects=[
                AnnotationObject(
                    id="nan1",
                    label_id=0,
                    geometry_type="bbox_xyxy",
                    geometry=(float("nan"), 50.0, 100.0, 100.0),
                    attributes={"label": "defect"},
                )
            ],
        )
        issues = codec.validate_annotations(doc)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any("not finite" in i for i in issues))


# ---------------------------------------------------------------------------
# Class mapping tests
# ---------------------------------------------------------------------------
class TestClassMapping(unittest.TestCase):
    """Constructor classes parameter controls label_id assignment."""

    def test_label_id_from_classes(self):
        codec = XLabelCodec(classes=["defect", "normal"])
        doc = codec.load_annotations(str(HBB_SAMPLE), IMG_W, IMG_H)
        for obj in doc.objects:
            self.assertEqual(obj.label_id, 0)  # "defect" is index 0

    def test_auto_label_id_without_classes(self):
        codec = XLabelCodec()
        doc = codec.load_annotations(str(HBB_SAMPLE), IMG_W, IMG_H)
        for obj in doc.objects:
            # First seen label "defect" gets id 0
            self.assertEqual(obj.label_id, 0)


if __name__ == "__main__":
    unittest.main()
