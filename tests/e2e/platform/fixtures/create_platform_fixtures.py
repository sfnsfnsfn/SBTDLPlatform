#!/usr/bin/env python
"""
Generate deterministic platform test fixtures for the Vision Algorithm Platform V4 MVP.

Usage:
    python tests/e2e/platform/fixtures/create_platform_fixtures.py

Output:
    tests/e2e/platform/fixtures/images/       — 7 PNG images
    tests/e2e/platform/fixtures/annotations/  — 7 X-AnyLabeling JSON files
    tests/e2e/platform/fixtures/expected_manifests/ — expected manifest files

All coordinates use L0 image pixels.
"""

import json
import os
import sys

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Version — dynamically import from app_info, fall back to known good value
# ---------------------------------------------------------------------------
try:
    from anylabeling.app_info import __version__
except ImportError:
    __version__ = "4.0.0-beta.7"

# ---------------------------------------------------------------------------
# Deterministic seed
# ---------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(HERE, "images")
ANNOTATIONS_DIR = os.path.join(HERE, "annotations")
MANIFESTS_DIR = os.path.join(HERE, "expected_manifests")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(ANNOTATIONS_DIR, exist_ok=True)
os.makedirs(MANIFESTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rect_ccw(x1, y1, x2, y2):
    """Convert axis-aligned diagonal corners to 4-point CCW polygon.

    X-AnyLabeling writes rectangles as 4-point CCW order:
      [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]

    The 2-point diagonal [[x1,y1], [x2,y2]] is deprecated.
    """
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _canonical_shape(label, points, shape_type, group_id=None, description="", flags=None):
    """Build a shape dict matching the canonical Shape.KEYS fields."""
    return {
        "label": label,
        "score": None,
        "points": points,
        "group_id": group_id,
        "difficult": False,
        "shape_type": shape_type,
        "flags": flags if flags is not None else {},
        "description": description,
        "attributes": {},
        "kie_linking": [],
    }


def _make_json(image_path, shapes, image_height, image_width, extra_flags=None, image_data_null=True):
    """Build an X-AnyLabeling-compatible JSON dict."""
    flags = {}
    if extra_flags:
        flags.update(extra_flags)
    return {
        "version": __version__,
        "flags": flags,
        "checked": False,
        "shapes": shapes,
        "imagePath": os.path.basename(image_path),
        "imageData": None if image_data_null else "",
        "imageHeight": image_height,
        "imageWidth": image_width,
    }


def save_image_and_json(name, img, shapes, height, width, extra_flags=None):
    """Save PNG image and corresponding X-AnyLabeling JSON.

    Parameters:
        height, width: image dimensions in L0 pixels (matches imageHeight/imageWidth).
    """
    img_path = os.path.join(IMAGES_DIR, f"{name}.png")
    json_path = os.path.join(ANNOTATIONS_DIR, f"{name}.json")

    cv2.imwrite(img_path, img)
    annotation = _make_json(img_path, shapes, height, width, extra_flags)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(annotation, f, indent=2, ensure_ascii=False)

    return img_path, json_path


# ---------------------------------------------------------------------------
# Fixture generators
# ---------------------------------------------------------------------------

def _create_classify_sample():
    """640x480 image with distinct color-block features; classification flags only."""
    h, w = 480, 640
    img = np.full((h, w, 3), (180, 180, 180), dtype=np.uint8)  # gray background

    # Four colored blocks representing different 'classes' of surface
    blocks = [
        (0, 0, 200, 200, (255, 100, 100)),       # top-left red
        (440, 0, 640, 200, (100, 255, 100)),      # top-right green
        (0, 280, 200, 480, (100, 100, 255)),      # bottom-left blue
        (440, 280, 640, 480, (255, 255, 100)),    # bottom-right yellow
    ]
    for x1, y1, x2, y2, color in blocks:
        cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)

    # Center circle as focal feature
    cv2.circle(img, (320, 240), 60, (255, 255, 255), -1)
    cv2.putText(img, "OK", (295, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    shapes = []  # classification fixtures have no shapes, only image flags
    extra_flags = {"defect_free": True, "lighting": "good"}
    return img, shapes, extra_flags


def _create_hbb_sample():
    """640x480 white background with 3 black axis-aligned rectangles (4-point CCW)."""
    h, w = 480, 640
    img = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)

    rects = [
        (50, 50, 150, 120),
        (200, 180, 350, 280),
        (400, 100, 580, 400),
    ]
    shapes = []
    for idx, (x1, y1, x2, y2) in enumerate(rects):
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
        # small white label marker
        cv2.putText(img, str(idx + 1), (x1 + 5, y1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        shapes.append(_canonical_shape(
            label="defect",
            points=_rect_ccw(x1, y1, x2, y2),
            shape_type="rectangle",
        ))

    return img, shapes, {}


def _create_obb_sample():
    """640x480 white background with 2 rotated rectangles (4-point polygons)."""
    h, w = 480, 640
    img = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)

    # Rotated rectangle 1: center (150, 150), size 120x60, rotated 30 deg
    center1 = (150, 150)
    rect1_points_int = np.array([
        [90, 120], [210, 120], [210, 180], [90, 180]
    ], dtype=np.int32)
    # Manual rotated rect
    angle = np.deg2rad(30)
    c, s = np.cos(angle), np.sin(angle)
    cx, cy = float(center1[0]), float(center1[1])
    half_w, half_h = 60.0, 30.0
    corners1 = np.array([
        [cx - half_w * c - half_h * s, cy - half_w * s + half_h * c],
        [cx + half_w * c - half_h * s, cy + half_w * s + half_h * c],
        [cx + half_w * c + half_h * s, cy + half_w * s - half_h * c],
        [cx - half_w * c + half_h * s, cy - half_w * s - half_h * c],
    ])
    cv2.fillPoly(img, [corners1.astype(np.int32)], (0, 0, 200))

    # Rotated rectangle 2: center (480, 350), size 100x40, rotated -20 deg
    angle2 = np.deg2rad(-20)
    cx2, cy2 = 480.0, 350.0
    half_w2, half_h2 = 50.0, 20.0
    c2, s2 = np.cos(angle2), np.sin(angle2)
    corners2 = np.array([
        [cx2 - half_w2 * c2 - half_h2 * s2, cy2 - half_w2 * s2 + half_h2 * c2],
        [cx2 + half_w2 * c2 - half_h2 * s2, cy2 + half_w2 * s2 + half_h2 * c2],
        [cx2 + half_w2 * c2 + half_h2 * s2, cy2 + half_w2 * s2 - half_h2 * c2],
        [cx2 - half_w2 * c2 + half_h2 * s2, cy2 - half_w2 * s2 - half_h2 * c2],
    ])
    cv2.fillPoly(img, [corners2.astype(np.int32)], (0, 150, 0))

    shapes = [
        _canonical_shape("rotated_defect", corners1.tolist(), "rotation"),
        _canonical_shape("rotated_defect", corners2.tolist(), "rotation"),
    ]

    return img, shapes, {}


def _create_polygon_sample():
    """640x480 white background with 2 irregular polygon shapes."""
    h, w = 480, 640
    img = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)

    # Irregular star-like polygon 1
    poly1 = np.array([
        [80, 60], [160, 40], [200, 100], [180, 160],
        [120, 190], [60, 150], [40, 100],
    ], dtype=np.int32)
    cv2.fillPoly(img, [poly1], (200, 80, 80))

    # Irregular blob-like polygon 2
    poly2 = np.array([
        [400, 300], [480, 260], [550, 310], [580, 380],
        [520, 440], [440, 450], [380, 400],
    ], dtype=np.int32)
    cv2.fillPoly(img, [poly2], (80, 200, 80))

    shapes = [
        _canonical_shape("irregular_defect", poly1.tolist(), "polygon"),
        _canonical_shape("irregular_defect", poly2.tolist(), "polygon"),
    ]

    return img, shapes, {}


def _create_pose_sample():
    """640x480 white background with 2 stick-figure-like keypoint sets."""
    h, w = 480, 640
    img = np.full((h, w, 3), (255, 255, 255), dtype=np.uint8)

    # Stick figure 1
    kpts1 = np.array([
        [150, 80],    # head
        [150, 140],   # neck
        [130, 180],   # left shoulder
        [170, 180],   # right shoulder
        [110, 240],   # left elbow
        [130, 300],   # left wrist
        [190, 240],   # right elbow
        [210, 280],   # right wrist
        [150, 200],   # hip
        [130, 260],   # left knee
        [110, 340],   # left ankle
        [170, 260],   # right knee
        [190, 360],   # right ankle
    ], dtype=np.int32)

    # Stick figure 2 (offset to right)
    kpts2 = np.array([
        [450, 100],   # head
        [450, 160],   # neck
        [430, 200],   # left shoulder
        [470, 200],   # right shoulder
        [410, 260],   # left elbow
        [440, 320],   # left wrist
        [490, 260],   # right elbow
        [510, 300],   # right wrist
        [450, 220],   # hip
        [430, 280],   # left knee
        [410, 360],   # left ankle
        [470, 280],   # right knee
        [490, 370],   # right ankle
    ], dtype=np.int32)

    # Draw stick figures as connected lines
    skeleton = [
        (0, 1), (1, 2), (1, 3), (2, 4), (4, 5),
        (3, 6), (6, 7), (1, 8), (8, 9), (9, 10),
        (8, 11), (11, 12),
    ]
    for kpts in (kpts1, kpts2):
        for a, b in skeleton:
            pt_a = tuple(int(v) for v in kpts[a])
            pt_b = tuple(int(v) for v in kpts[b])
            cv2.line(img, pt_a, pt_b, (0, 0, 0), 3)
        for pt in kpts:
            cv2.circle(img, tuple(int(v) for v in pt), 5, (0, 0, 255), -1)

    shapes = [
        _canonical_shape("person", kpts1.tolist(), "point"),
        _canonical_shape("person", kpts2.tolist(), "point"),
    ]

    return img, shapes, {}


def _create_empty_background_sample():
    """640x480 plain gray image — no shapes, only image-level flags."""
    h, w = 480, 640
    img = np.full((h, w, 3), (128, 128, 128), dtype=np.uint8)
    shapes = []
    extra_flags = {"empty": True, "note": "background test image"}
    return img, shapes, extra_flags


def _create_ci_large_sample():
    """8192x8192 synthetic image with grid lines and 3 known rectangles (4-point CCW)."""
    h, w = 8192, 8192
    img = np.full((h, w, 3), (40, 40, 40), dtype=np.uint8)

    # Grid lines every 512 px
    grid_spacing = 512
    for x in range(0, w, grid_spacing):
        cv2.line(img, (x, 0), (x, h - 1), (60, 60, 60), 1)
    for y in range(0, h, grid_spacing):
        cv2.line(img, (0, y), (w - 1, y), (60, 60, 60), 1)

    # Coordinate axes
    cv2.line(img, (0, 0), (w - 1, h - 1), (30, 30, 30), 2)  # diagonal ref

    # 3 HBB rectangles at known positions
    rects = [
        (100, 100, 500, 400),
        (4000, 4000, 4500, 4300),
        (7500, 7500, 8000, 8000),
    ]
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    shapes = []
    for idx, ((x1, y1, x2, y2), color) in enumerate(zip(rects, colors)):
        cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
        # Label text at center
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        cv2.putText(img, f"R{idx + 1}", (cx - 20, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        shapes.append(_canonical_shape(
            label="large_defect",
            points=_rect_ccw(x1, y1, x2, y2),
            shape_type="rectangle",
        ))

    return img, shapes, {}


# ---------------------------------------------------------------------------
# FIXTURES registry: (name, generator_fn, height, width)
# ---------------------------------------------------------------------------

FIXTURES = [
    ("classify_sample",           _create_classify_sample,          480, 640),
    ("hbb_sample",                _create_hbb_sample,               480, 640),
    ("obb_sample",                _create_obb_sample,               480, 640),
    ("polygon_sample",            _create_polygon_sample,           480, 640),
    ("pose_sample",               _create_pose_sample,              480, 640),
    ("empty_background",          _create_empty_background_sample,  480, 640),
    ("ci_large_sample",           _create_ci_large_sample,          8192, 8192),
]


def main():
    print("=" * 70)
    print("Vision Platform V4 MVP — Fixture Generator")
    print(f"Seed: {SEED}")
    print(f"Version: {__version__}")
    print("=" * 70)
    print()

    results = []

    for name, generator_fn, height, width in FIXTURES:
        img, shapes, extra_flags = generator_fn()
        img_path, json_path = save_image_and_json(name, img, shapes, height, width, extra_flags)

        file_size_mb = os.path.getsize(img_path) / (1024 * 1024)
        results.append({
            "name": name,
            "image": img_path,
            "json": json_path,
            "dimensions": f"{width}x{height}",
            "shapes_count": len(shapes),
            "file_size_mb": file_size_mb,
        })
        print(f"  [{name}] {width}x{height}, {len(shapes)} shapes, {file_size_mb:.2f} MB")
        print(f"         image: {img_path}")
        print(f"         json:  {json_path}")

    print()
    print("-" * 70)
    print(f"Total: {len(results)} fixtures created")
    print(f"Images dir:      {IMAGES_DIR}")
    print(f"Annotations dir: {ANNOTATIONS_DIR}")
    print(f"Manifests dir:   {MANIFESTS_DIR}")
    print("=" * 70)

    # Write fixture summary manifest
    summary = {
        "generator": "create_platform_fixtures.py",
        "seed": SEED,
        "fixtures": results,
    }
    summary_path = os.path.join(MANIFESTS_DIR, "fixture_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written to: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
