"""Tests for annotation_adapter."""
import pytest
from anylabeling.platform.application.annotation_adapter import (
    get_allowed_shape_types,
    shape_type_to_geometry_type,
    geometry_type_to_shape_type,
    shapes_to_annotation_doc,
    annotation_doc_to_shapes,
)
from anylabeling.platform.domain.annotation import AnnotationDocument


class TestTaskFamilyMapping:
    def test_detection_hbb_allows_rectangle(self):
        assert get_allowed_shape_types("detection_hbb") == ["rectangle"]

    def test_detection_obb_allows_rotation(self):
        assert get_allowed_shape_types("detection_obb") == ["rotation"]

    def test_instance_segmentation_allows_polygon(self):
        assert get_allowed_shape_types("instance_segmentation") == ["polygon"]

    def test_pose_allows_point(self):
        assert get_allowed_shape_types("pose") == ["point"]

    def test_classification_allows_nothing(self):
        assert get_allowed_shape_types("classification") == []

    def test_anomaly_allows_rect_and_poly(self):
        assert get_allowed_shape_types("anomaly") == ["rectangle", "polygon"]

    def test_unknown_family_empty(self):
        assert get_allowed_shape_types("nonexistent") == []


class TestShapeTypeMapping:
    def test_rectangle_to_bbox_xyxy(self):
        assert shape_type_to_geometry_type("rectangle") == "bbox_xyxy"

    def test_rotation_to_obb_polygon(self):
        assert shape_type_to_geometry_type("rotation") == "obb_polygon"

    def test_point_to_keypoints(self):
        assert shape_type_to_geometry_type("point") == "keypoints"

    def test_polygon_roundtrip(self):
        assert shape_type_to_geometry_type("polygon") == "polygon"

    def test_bbox_xyxy_reverse(self):
        assert geometry_type_to_shape_type("bbox_xyxy") == "rectangle"

    def test_obb_polygon_reverse(self):
        assert geometry_type_to_shape_type("obb_polygon") == "rotation"

    def test_unknown_defaults_to_polygon(self):
        assert shape_type_to_geometry_type("cuboid") == "polygon"


class MockQPointF:
    def __init__(self, x, y):
        self._x = float(x)
        self._y = float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class MockShape:
    def __init__(self, shape_type, label, points, group_id=None,
                 difficult=False, description=""):
        self.shape_type = shape_type
        self.label = label
        self.points = points
        self.group_id = group_id
        self.difficult = difficult
        self.description = description


class TestConversionRoundtrip:
    def test_rectangle(self):
        shapes = [
            MockShape("rectangle", "person",
                      [MockQPointF(10, 20), MockQPointF(100, 20),
                       MockQPointF(100, 200), MockQPointF(10, 200)])
        ]
        doc = shapes_to_annotation_doc(shapes, "img1", 640, 480, {"person": 0})
        assert len(doc.objects) == 1
        assert doc.objects[0].geometry_type == "bbox_xyxy"
        assert doc.objects[0].geometry == (10, 20, 100, 200)

        result = annotation_doc_to_shapes(doc)
        assert len(result) == 1
        assert result[0]["shape_type"] == "rectangle"
        assert result[0]["label"] == "person"
        assert result[0]["points"] == [(10, 20), (100, 20), (100, 200), (10, 200)]

    def test_polygon(self):
        shapes = [
            MockShape("polygon", "region",
                      [MockQPointF(1, 2), MockQPointF(3, 4), MockQPointF(5, 6)])
        ]
        doc = shapes_to_annotation_doc(shapes, "img2", 100, 100, {"region": 0})
        assert doc.objects[0].geometry_type == "polygon"
        assert doc.objects[0].geometry == [(1, 2), (3, 4), (5, 6)]

    def test_empty_shapes(self):
        doc = shapes_to_annotation_doc([], "img3", 100, 100, {})
        assert doc.objects == []

    def test_empty_doc_roundtrip(self):
        doc = AnnotationDocument(asset_id="img4", image_width=100, image_height=100, objects=[])
        result = annotation_doc_to_shapes(doc)
        assert result == []
