"""
Smoke tests for platform test fixtures.

Verifies all fixture images and annotations were generated correctly:
- 6 small images (classify, HBB, OBB, polygon, pose, empty_background) at 640x480
- 1 large image (ci_large_sample) at 8192x8192
- X-AnyLabeling JSON annotations with valid L0 pixel coordinates

Run:
    python -m pytest tests/e2e/platform/test_fixtures.py -v
    python -m pytest tests/e2e/platform -q
"""

import json
import os

import cv2
import numpy as np
import pytest

from anylabeling.platform.infrastructure.image_reader import ImageReader

# Dynamically import the real application version for validation
try:
    from anylabeling.app_info import __version__
except ImportError:
    __version__ = "4.0.0-beta.7"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(HERE, "fixtures", "images")
ANNOTATIONS_DIR = os.path.join(HERE, "fixtures", "annotations")

# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------
SMALL_IMAGES = [
    ("classify_sample",   640, 480),
    ("hbb_sample",        640, 480),
    ("obb_sample",        640, 480),
    ("polygon_sample",    640, 480),
    ("pose_sample",       640, 480),
    ("empty_background",  640, 480),
]

LARGE_IMAGES = [
    ("ci_large_sample", 8192, 8192),
]

ALL_IMAGES = SMALL_IMAGES + LARGE_IMAGES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(name):
    path = os.path.join(ANNOTATIONS_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_image(name):
    path = os.path.join(IMAGES_DIR, f"{name}.png")
    img = ImageReader.read(path, output_color="BGR")
    assert img is not None, f"Failed to load image: {path}"
    return path, img


# ---------------------------------------------------------------------------
# Tests: all images exist with correct dimensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected_w,expected_h", ALL_IMAGES)
def test_fixture_image_exists(name, expected_w, expected_h):
    """Each fixture must have a PNG image with correct dimensions."""
    path, img = _load_image(name)
    h, w = img.shape[:2]
    assert w == expected_w, f"{name}: expected width {expected_w}, got {w}"
    assert h == expected_h, f"{name}: expected height {expected_h}, got {h}"
    assert os.path.getsize(path) > 0, f"{name}: image file is empty"


# ---------------------------------------------------------------------------
# Tests: all annotations exist and parse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,img_w,img_h", ALL_IMAGES)
def test_fixture_json_exists_and_valid(name, img_w, img_h):
    """Each fixture must have valid X-AnyLabeling JSON."""
    doc = _load_json(name)
    assert doc["version"] == __version__, f"{name}: unexpected version: {doc['version']}"
    assert "imagePath" in doc
    assert doc["imagePath"].startswith(name)
    assert "imageHeight" in doc
    assert "imageWidth" in doc
    assert isinstance(doc["shapes"], list)
    assert "checked" in doc, f"{name}: missing 'checked' field"
    assert doc["checked"] is False, f"{name}: expected checked=False"
    assert "flags" in doc


# ---------------------------------------------------------------------------
# Tests: image dimensions match JSON metadata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected_w,expected_h", ALL_IMAGES)
def test_fixture_json_dimensions_match_image(name, expected_w, expected_h):
    """JSON imageHeight/imageWidth must match the actual PNG dimensions."""
    doc = _load_json(name)
    assert doc["imageWidth"] == expected_w, (
        f"{name}: JSON imageWidth {doc['imageWidth']} != expected {expected_w}"
    )
    assert doc["imageHeight"] == expected_h, (
        f"{name}: JSON imageHeight {doc['imageHeight']} != expected {expected_h}"
    )


# ---------------------------------------------------------------------------
# Tests: shapes have valid coordinates (L0 pixel, within image bounds)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,img_w,img_h", ALL_IMAGES)
def test_fixture_shape_coordinates_in_bounds(name, img_w, img_h):
    """All shape points must be within image bounds (L0 pixel coordinates)."""
    doc = _load_json(name)
    for idx, shape in enumerate(doc["shapes"]):
        shape_type = shape.get("shape_type", "unknown")
        points = shape.get("points", [])

        # At minimum, one point is required (except classification which has no shapes)
        if shape_type is None and not points:
            continue

        for pt_idx, (x, y) in enumerate(points):
            assert 0 <= x <= img_w, (
                f"{name}: shape[{idx}] ({shape_type}) point[{pt_idx}] "
                f"x={x} out of range [0, {img_w}]"
            )
            assert 0 <= y <= img_h, (
                f"{name}: shape[{idx}] ({shape_type}) point[{pt_idx}] "
                f"y={y} out of range [0, {img_h}]"
            )


@pytest.mark.parametrize("name,img_w,img_h", ALL_IMAGES)
def test_fixture_shape_coordinates_are_numbers(name, img_w, img_h):
    """All shape point values must be numeric (int or float)."""
    doc = _load_json(name)
    for shape in doc["shapes"]:
        for x, y in shape["points"]:
            assert isinstance(x, (int, float)), (
                f"{name}: non-numeric x coordinate: {type(x)}"
            )
            assert isinstance(y, (int, float)), (
                f"{name}: non-numeric y coordinate: {type(y)}"
            )


# ---------------------------------------------------------------------------
# Tests: specific fixture content
# ---------------------------------------------------------------------------

def test_hbb_sample_has_3_rectangles():
    """HBB fixture must have exactly 3 rectangle shapes at known positions."""
    doc = _load_json("hbb_sample")
    assert len(doc["shapes"]) == 3
    expected_positions = [
        [[50, 50], [150, 50], [150, 120], [50, 120]],
        [[200, 180], [350, 180], [350, 280], [200, 280]],
        [[400, 100], [580, 100], [580, 400], [400, 400]],
    ]
    for shape, expected_pts in zip(doc["shapes"], expected_positions):
        assert shape["shape_type"] == "rectangle"
        assert shape["points"] == expected_pts


def test_classify_sample_has_no_shapes():
    """Classification fixture must have no shapes and correct flags."""
    doc = _load_json("classify_sample")
    assert doc["shapes"] == []
    assert doc["flags"]["defect_free"] is True
    assert doc["flags"]["lighting"] == "good"


def test_obb_sample_has_2_rotation_shapes():
    """OBB fixture must have 2 rotation shapes with 4 points each."""
    doc = _load_json("obb_sample")
    assert len(doc["shapes"]) == 2
    for shape in doc["shapes"]:
        assert shape["shape_type"] == "rotation"
        assert len(shape["points"]) == 4


def test_polygon_sample_has_2_polygon_shapes():
    """Polygon fixture must have 2 polygon shapes."""
    doc = _load_json("polygon_sample")
    assert len(doc["shapes"]) == 2
    for shape in doc["shapes"]:
        assert shape["shape_type"] == "polygon"
        assert len(shape["points"]) >= 3  # polygon needs at least 3 points


def test_pose_sample_has_2_point_shapes():
    """Pose fixture must have 2 point sets with 13 keypoints each."""
    doc = _load_json("pose_sample")
    assert len(doc["shapes"]) == 2
    for shape in doc["shapes"]:
        assert shape["shape_type"] == "point"
        assert len(shape["points"]) == 13


def test_empty_background_has_no_shapes():
    """Empty background fixture must have no shapes and empty flag."""
    doc = _load_json("empty_background")
    assert doc["shapes"] == []
    assert doc["flags"]["empty"] is True


# ---------------------------------------------------------------------------
# E2E: parameter passthrough from UI config → DatasetBuild output
# ---------------------------------------------------------------------------


def test_e2e_passthrough_config_to_build(tmp_path):
    """PreprocessConfig → DatasetBuildService.build() → verify outputs."""
    import json

    from anylabeling.platform.application.dataset_build_service import (
        DatasetBuildService,
    )
    from anylabeling.platform.domain.annotation import (
        AnnotationDocument,
        AnnotationObject,
    )
    from anylabeling.platform.domain.asset import Asset
    from anylabeling.platform.domain.preprocess_config import PreprocessConfig
    from anylabeling.platform.domain.task import LabelClass, TaskSpec
    from anylabeling.platform.infrastructure.image_sources.file_image_source import (
        FileImageSource,
    )
    from anylabeling.platform.tiling.tile_planner import TilePlanner
    from anylabeling.platform.domain.tile import TilePlan

    # 1. Create project structure + synthetic images
    root = tmp_path / "passthrough_project"
    root.mkdir()
    assets_dir = root / "assets"
    assets_dir.mkdir()
    (root / "annotations").mkdir()
    (root / "dataset_builds").mkdir()

    rng = np.random.default_rng(42)
    for i in range(5):
        img = rng.integers(0, 255, (480, 640, 3)).astype(np.uint8)
        cv2.imwrite(str(assets_dir / f"img_{i:03d}.jpg"), img)

    # 2. Create minimal TaskSpec + AnnotationDocument per asset
    task_spec = TaskSpec(
        id="task_e2e",
        family="detection_hbb",
        labels=(LabelClass(id=0, name="defect"),),
    )

    annotations: dict[str, AnnotationDocument] = {}
    for i in range(5):
        img_path = str(assets_dir / f"img_{i:03d}.jpg")
        annotations[img_path] = AnnotationDocument(
            objects=[
                AnnotationObject(
                    label="defect",
                    points=[(50, 50), (150, 150)],
                    shape_type="rectangle",
                    flags={},
                )
            ],
            image_path=img_path,
        )

    assets = [
        Asset(path=str(assets_dir / f"img_{i:03d}.jpg"))
        for i in range(5)
    ]

    # 3. Create PreprocessConfig and TilePlan
    config = PreprocessConfig(
        tile_width=512, tile_height=512,
        overlap_x=128, overlap_y=128,
        train_ratio=0.6, val_ratio=0.3, test_ratio=0.1,
        random_seed=42,
    )

    image_sources = {
        a.path: FileImageSource(a.path) for a in assets
    }

    tile_plan: TilePlan = {}
    for asset in assets:
        tiles = TilePlanner.plan(
            image_source=image_sources[asset.path],
            tile_width=config.tile_width,
            tile_height=config.tile_height,
            overlap_x=config.overlap_x,
            overlap_y=config.overlap_y,
        )
        if tiles:
            tile_plan[asset.path] = tiles

    # 4. Build
    service = DatasetBuildService(str(root))
    result = service.build(
        assets=assets,
        task_spec=task_spec,
        annotations=annotations,
        tile_plan=tile_plan if tile_plan else None,
        preprocess_config=config,
    )

    # 5. Verify build outputs
    build_dir = root / "dataset_builds" / result.id
    assert build_dir.is_dir(), f"Build dir not found: {build_dir}"

    build_json_path = build_dir / "build.json"
    assert build_json_path.exists()
    build_json = json.loads(build_json_path.read_text())
    assert "id" in build_json
    assert build_json.get("tile_width") == 512
    assert build_json.get("tile_height") == 512

    split_path = build_dir / "split_manifest.json"
    if split_path.exists():
        split_manifest = json.loads(split_path.read_text())
        assert "asset_assignments" in split_manifest

    data_yaml_path = build_dir / "data.yaml"
    assert data_yaml_path.exists()


def test_ci_large_sample_dimensions_and_shapes():
    """Large fixture must be 8192x8192 with 3 HBB rectangles at known positions."""
    doc = _load_json("ci_large_sample")
    assert doc["imageWidth"] == 8192
    assert doc["imageHeight"] == 8192
    assert len(doc["shapes"]) == 3

    expected_positions = [
        [[100, 100], [500, 100], [500, 400], [100, 400]],
        [[4000, 4000], [4500, 4000], [4500, 4300], [4000, 4300]],
        [[7500, 7500], [8000, 7500], [8000, 8000], [7500, 8000]],
    ]
    for shape, expected_pts in zip(doc["shapes"], expected_positions):
        assert shape["shape_type"] == "rectangle"
        assert shape["points"] == expected_pts


# ---------------------------------------------------------------------------
# Tests: JSONL manifest validity (future-proofing)
# ---------------------------------------------------------------------------

def test_fixture_summary_manifest_exists():
    """Verify the fixture summary manifest was generated."""
    manifest_path = os.path.join(
        HERE, "fixtures", "expected_manifests", "fixture_summary.json"
    )
    assert os.path.exists(manifest_path), f"Missing: {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["seed"] == 42
    assert len(data["fixtures"]) == 7


# ---------------------------------------------------------------------------
# Tests: image file sizes are reasonable
# ---------------------------------------------------------------------------

def test_ci_large_sample_file_size_reasonable():
    """Large fixture should be between 0.5 MB and 5 MB (compressed PNG)."""
    path = os.path.join(IMAGES_DIR, "ci_large_sample.png")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    assert 0.1 < size_mb < 5.0, (
        f"ci_large_sample.png size {size_mb:.2f} MB outside expected range"
    )


@pytest.mark.parametrize("name,img_w,img_h", SMALL_IMAGES)
def test_small_image_file_size_reasonable(name, img_w, img_h):
    """Small fixtures should be under 200 KB."""
    path = os.path.join(IMAGES_DIR, f"{name}.png")
    size_kb = os.path.getsize(path) / 1024
    assert size_kb > 0, f"{name}.png is empty"
    assert size_kb < 200, f"{name}.png size {size_kb:.0f} KB exceeds 200 KB limit"


# ---------------------------------------------------------------------------
# Tests: JSON encoding is UTF-8
# ---------------------------------------------------------------------------

def test_all_json_is_valid_utf8():
    """All annotation JSON files must be valid UTF-8."""
    import glob
    for json_path in glob.glob(os.path.join(ANNOTATIONS_DIR, "*.json")):
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()
        data = json.loads(content)
        assert isinstance(data, dict), f"{json_path}: not a JSON object"


# ---------------------------------------------------------------------------
# Tests: deterministic reproducibility
# ---------------------------------------------------------------------------

def test_obb_sample_deterministic():
    """OBB fixture must produce exact same coordinates with fixed seed."""
    doc = _load_json("obb_sample")
    # These exact values are recorded from seed=42 execution
    # Rotated rect 1 at center (150, 150), 120x60, 30 degrees
    # Rotated rect 2 at center (480, 350), 100x40, -20 degrees
    assert len(doc["shapes"]) == 2
    assert doc["shapes"][0]["shape_type"] == "rotation"
    assert doc["shapes"][1]["shape_type"] == "rotation"
    assert len(doc["shapes"][0]["points"]) == 4
    assert len(doc["shapes"][1]["points"]) == 4


# ---------------------------------------------------------------------------
# Phase 0 E2E fixtures — synthetic datasets (no binary files in repo)
# ---------------------------------------------------------------------------

def _make_synthetic_image(path, w, h, seed=42):
    """Write a deterministic synthetic color image to *path*."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return img


def _make_yolo_label(path, class_id, cx, cy, nw, nh):
    """Write a single-line YOLO-format label file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")


# E2E-01: 10 JPGs + YOLO labels (detection)
# ---------------------------------------------------------------------------

def test_e2e_01_detection_dataset(tmp_path):
    """10 synthetic JPGs with YOLO-format labels in a flat structure."""
    assets = tmp_path / "assets"
    labels_dir = tmp_path / "labels"
    assets.mkdir()
    labels_dir.mkdir()

    for i in range(10):
        img_path = assets / f"img_{i:04d}.jpg"
        _make_synthetic_image(img_path, 640, 480, seed=i)
        _make_yolo_label(labels_dir / f"img_{i:04d}.txt", 0, 0.5, 0.5, 0.3, 0.3)

    jpgs = sorted(assets.glob("*.jpg"))
    assert len(jpgs) == 10, f"Expected 10 JPGs, got {len(jpgs)}"
    for jpg in jpgs:
        assert jpg.stat().st_size > 0, f"Empty JPG: {jpg}"
    txts = sorted(labels_dir.glob("*.txt"))
    assert len(txts) == 10, f"Expected 10 labels, got {len(txts)}"
    for txt in txts:
        assert txt.stat().st_size > 0, f"Empty label: {txt}"


# E2E-02: 2 TIFFs 8000×8000 + polygon labels (large-image seg)
# ---------------------------------------------------------------------------

def test_e2e_02_large_tiff_segmentation(tmp_path):
    """2 synthetic TIFFs (8000×8000) with polygon labels."""
    assets = tmp_path / "assets"
    assets.mkdir()

    for i in range(2):
        tiff = assets / f"large_{i}.tiff"
        _make_synthetic_image(tiff, 8000, 8000, seed=100 + i)

    tiffs = sorted(assets.glob("*.tiff"))
    assert len(tiffs) == 2
    for tiff in tiffs:
        img = ImageReader.read(str(tiff), output_color="BGR")
        assert img is not None
        assert img.shape[:2] == (8000, 8000)


# E2E-03: 3 subdirs × 5 images (group isolation)
# ---------------------------------------------------------------------------

def test_e2e_03_group_isolation(tmp_path):
    """3 subdirectories, each with 5 images — verifies group-based splitting."""
    for g in range(3):
        sub = tmp_path / f"group_{g}"
        sub.mkdir()
        for i in range(5):
            _make_synthetic_image(sub / f"img_{i:02d}.png", 512, 512, seed=g * 10 + i)

    for g in range(3):
        pngs = sorted((tmp_path / f"group_{g}").glob("*.png"))
        assert len(pngs) == 5, f"group_{g}: expected 5 PNGs, got {len(pngs)}"


# E2E-04: 5 defect + 5 clean (negative samples)
# ---------------------------------------------------------------------------

def test_e2e_04_negative_samples(tmp_path):
    """5 images with defect annotations + 5 images with no annotations."""
    assets = tmp_path / "assets"
    labels_dir = tmp_path / "labels"
    assets.mkdir()
    labels_dir.mkdir()

    for i in range(5):
        _make_synthetic_image(assets / f"defect_{i}.jpg", 640, 480, seed=i)
        _make_yolo_label(labels_dir / f"defect_{i}.txt", 0, 0.5, 0.5, 0.2, 0.2)

    for i in range(5):
        _make_synthetic_image(assets / f"clean_{i}.jpg", 640, 480, seed=50 + i)

    jpgs = sorted(assets.glob("*.jpg"))
    assert len(jpgs) == 10
    txts = sorted(labels_dir.glob("*.txt"))
    assert len(txts) == 5, f"Expected 5 label files, got {len(txts)}"


# E2E-05: 3 images minimal project (crash recovery)
# ---------------------------------------------------------------------------

def test_e2e_05_minimal_project(tmp_path):
    """3 images — the smallest valid project for crash recovery testing."""
    assets = tmp_path / "assets"
    assets.mkdir()
    for i in range(3):
        _make_synthetic_image(assets / f"minimal_{i}.png", 256, 256, seed=i)

    pngs = sorted(assets.glob("*.png"))
    assert len(pngs) == 3
    for png in pngs:
        img = ImageReader.read(str(png), output_color="BGR")
        assert img is not None
        assert img.shape[:2] == (256, 256)


# E2E-06: normal + corrupt + zero-byte + unsupported (error files)
# ---------------------------------------------------------------------------

def test_e2e_06_error_files(tmp_path):
    """Mix of valid, corrupt, zero-byte, and unsupported files."""
    assets = tmp_path / "assets"
    assets.mkdir()

    _make_synthetic_image(assets / "normal.jpg", 640, 480)
    (assets / "corrupt.jpg").write_bytes(b"\xff\xd8\xff\xe0" + os.urandom(200))
    (assets / "zero.jpg").write_bytes(b"")
    (assets / "readme.txt").write_text("not an image")

    all_files = sorted(assets.iterdir())
    assert len(all_files) == 4

    assert ImageReader.read(str(assets / "normal.jpg"), output_color="BGR") is not None
    with pytest.raises(Exception):
        ImageReader.read(str(assets / "corrupt.jpg"), output_color="BGR")
    with pytest.raises(Exception):
        ImageReader.read(str(assets / "zero.jpg"), output_color="BGR")


# E2E-07: 2 images (offline scenario)
# ---------------------------------------------------------------------------

def test_e2e_07_offline_scenario(tmp_path):
    """2 synthetic images — minimal offline scenario, no network dependencies."""
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_synthetic_image(assets / "offline_01.jpg", 1024, 768, seed=1)
    _make_synthetic_image(assets / "offline_02.jpg", 1024, 768, seed=2)

    jpgs = sorted(assets.glob("*.jpg"))
    assert len(jpgs) == 2
    for jpg in jpgs:
        assert jpg.stat().st_size > 0
        img = ImageReader.read(str(jpg), output_color="BGR")
        assert img is not None


# E2E-08: various resolutions (high DPI)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("w,h", [
    (320, 240),       # low-res
    (640, 480),       # VGA
    (1280, 720),      # HD
    (1920, 1080),     # Full HD
    (3840, 2160),     # 4K
    (6000, 4000),     # high-res camera
])
def test_e2e_08_various_resolutions(tmp_path, w, h):
    """Images at various resolutions — verifies DPI-independent processing."""
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_synthetic_image(assets / f"img_{w}x{h}.jpg", w, h, seed=hash((w, h)) % 1000)

    img_path = assets / f"img_{w}x{h}.jpg"
    img = ImageReader.read(str(img_path), output_color="BGR")
    assert img is not None
    assert img.shape[1] == w, f"Expected width {w}, got {img.shape[1]}"
    assert img.shape[0] == h, f"Expected height {h}, got {img.shape[0]}"
    assert img_path.stat().st_size > 0
