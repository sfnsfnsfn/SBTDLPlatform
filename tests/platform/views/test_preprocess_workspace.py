"""Tests for PreprocessWorkspace — tile config, split validation, augmentations."""
import sys
import pytest

pytest.importorskip("PyQt6")


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# PreprocessConfig domain model tests (no PyQt needed)
# ---------------------------------------------------------------------------


class TestPreprocessConfig:
    """Frozen PreprocessConfig with sensible defaults."""

    def test_default_values(self):
        from anylabeling.platform.domain.preprocess_config import PreprocessConfig
        cfg = PreprocessConfig()
        assert cfg.tile_width == 1024
        assert cfg.tile_height == 1024
        assert cfg.overlap_x == 256
        assert cfg.overlap_y == 256
        assert cfg.edge_mode == "crop"
        assert cfg.split_strategy == "random_by_asset"
        assert cfg.train_ratio == 0.7
        assert cfg.val_ratio == 0.2
        assert cfg.test_ratio == 0.1
        assert cfg.random_seed == 42
        assert cfg.augmentations == frozenset()

    def test_is_frozen(self):
        from anylabeling.platform.domain.preprocess_config import PreprocessConfig
        cfg = PreprocessConfig()
        with pytest.raises(Exception):
            cfg.tile_width = 512  # type: ignore[misc]

    def test_custom_values(self):
        from anylabeling.platform.domain.preprocess_config import PreprocessConfig
        cfg = PreprocessConfig(
            tile_width=512, tile_height=512,
            overlap_x=128, overlap_y=128,
            edge_mode="pad", split_strategy="random_by_tile",
            train_ratio=0.8, val_ratio=0.1, test_ratio=0.1,
            random_seed=123,
            augmentations=frozenset({"hflip", "rotate"}),
        )
        assert cfg.tile_width == 512
        assert cfg.edge_mode == "pad"
        assert cfg.augmentations == frozenset({"hflip", "rotate"})

    def test_split_ratios_sum_one(self):
        """validate_split_ratios accepts valid ratios."""
        from anylabeling.platform.domain.preprocess_config import (
            PreprocessConfig,
            validate_split_ratios,
        )
        issues = validate_split_ratios(0.7, 0.2, 0.1)
        assert len(issues) == 0

    def test_split_ratios_sum_not_one(self):
        """validate_split_ratios rejects ratios that don't sum to 1.0."""
        from anylabeling.platform.domain.preprocess_config import (
            validate_split_ratios,
        )
        issues = validate_split_ratios(0.5, 0.3, 0.1)
        assert len(issues) > 0

    def test_split_ratios_negative(self):
        """validate_split_ratios rejects negative ratios."""
        from anylabeling.platform.domain.preprocess_config import (
            validate_split_ratios,
        )
        issues = validate_split_ratios(-0.1, 0.5, 0.6)
        assert len(issues) > 0

    def test_estimate_tiles(self):
        """Estimate tile count for a given image size and config."""
        from anylabeling.platform.domain.preprocess_config import PreprocessConfig
        cfg = PreprocessConfig(tile_width=1024, tile_height=1024, overlap_x=256, overlap_y=256)
        tiles = PreprocessConfig.estimate_tiles(cfg, 3000, 2000)
        # stride = 1024 - 256 = 768
        # tiles_x = ceil((3000 - 256) / 768) = ceil(2744/768) = ceil(3.57) = 4
        # tiles_y = ceil((2000 - 256) / 768) = ceil(1744/768) = ceil(2.27) = 3
        # total = 12
        assert tiles > 0
        assert tiles == 12


# ---------------------------------------------------------------------------
# SplitManifest tests (no PyQt needed)
# ---------------------------------------------------------------------------


class TestSplitManifest:
    """Frozen SplitManifest dataclass."""

    def test_creation(self):
        from anylabeling.platform.domain.split_manifest import SplitManifest
        m = SplitManifest(
            strategy="random_by_asset",
            train_ratio=0.7, val_ratio=0.2, test_ratio=0.1,
            random_seed=42,
            asset_assignments={"img1": "train", "img2": "val"},
        )
        assert m.strategy == "random_by_asset"
        assert m.asset_assignments["img1"] == "train"

    def test_is_frozen(self):
        from anylabeling.platform.domain.split_manifest import SplitManifest
        m = SplitManifest(
            strategy="random_by_asset",
            train_ratio=0.7, val_ratio=0.2, test_ratio=0.1,
            random_seed=42,
            asset_assignments={},
        )
        with pytest.raises(Exception):
            m.train_ratio = 0.5  # type: ignore[misc]

    def test_split_counts(self):
        """compute_split_counts returns expected train/val/test counts."""
        from anylabeling.platform.domain.split_manifest import SplitManifest
        m = SplitManifest(
            strategy="random_by_asset",
            train_ratio=0.7, val_ratio=0.2, test_ratio=0.1,
            random_seed=42,
            asset_assignments={},
        )
        train, val, test = SplitManifest.compute_split_counts(m, 100)
        assert train == 70
        assert val == 20
        assert test == 10

    def test_split_counts_small_total(self):
        """compute_split_counts handles small totals gracefully."""
        from anylabeling.platform.domain.split_manifest import SplitManifest
        m = SplitManifest(
            strategy="random_by_asset",
            train_ratio=0.7, val_ratio=0.2, test_ratio=0.1,
            random_seed=42,
            asset_assignments={},
        )
        train, val, test = SplitManifest.compute_split_counts(m, 5)
        assert train + val + test == 5


# ---------------------------------------------------------------------------
# PreprocessWorkspace widget tests (requires PyQt6)
# ---------------------------------------------------------------------------


class TestPreprocessWorkspaceWidget:
    """PreprocessWorkspace UI controls."""

    def test_create_widget(self, qapp):
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        assert ws is not None

    def test_build_button_emits_signal(self, qapp):
        """build_requested signal emits PreprocessConfig when build is clicked."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        from anylabeling.platform.domain.preprocess_config import PreprocessConfig

        ws = PreprocessWorkspace()
        emitted = []

        def on_build(config):
            emitted.append(config)

        ws.build_requested.connect(on_build)

        # Enable the build button (set assets)
        ws.set_total_assets(1)
        ws.set_large_images(["fake/path/img1.jpg"])
        ws._build_btn.click()

        assert len(emitted) == 1
        assert isinstance(emitted[0], PreprocessConfig)

    def test_build_button_disabled_without_images(self, qapp):
        """Build button is disabled when no large images are loaded."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        assert not ws._build_btn.isEnabled()

    def test_tile_params_update_preview(self, qapp):
        """Changing tile width/height updates the estimated tile count preview."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        ws.set_large_images(["fake/3000x2000.jpg"])
        ws._tile_width_sb.setValue(512)
        ws._tile_height_sb.setValue(512)
        preview_text = ws._tile_preview_label.text()
        # Should contain some estimate
        assert len(preview_text) > 0

    def test_split_ratio_validation(self, qapp):
        """Invalid split ratios are detected."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()

        # Set invalid ratios
        ws._train_ratio_sb.setValue(0.5)
        ws._val_ratio_sb.setValue(0.3)
        ws._test_ratio_sb.setValue(0.1)
        issues = ws._validate_current_split()
        assert len(issues) > 0

    def test_edge_mode_combo_has_options(self, qapp):
        """Edge mode combo has the expected options."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        assert ws._edge_mode_combo.count() >= 3  # strict, crop, pad

    def test_split_strategy_combo_has_options(self, qapp):
        """Split strategy combo has the expected options."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        strategies = {
            ws._split_strategy_combo.itemText(i)
            for i in range(ws._split_strategy_combo.count())
        }
        assert "random_by_asset" in strategies

    def test_augmentation_checkboxes(self, qapp):
        """Augmentation checkboxes exist and can be toggled."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        assert ws._hflip_cb is not None
        assert ws._vflip_cb is not None
        assert ws._brightness_cb is not None
        assert ws._rotate_cb is not None

    def test_build_enabled_with_normal_images(self, qapp):
        """Build button is enabled when assets exist but no large images."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        ws.set_total_assets(5)
        ws.set_large_images([])
        assert ws._build_btn.isEnabled()

    def test_build_disabled_with_no_assets(self, qapp):
        """Build button is disabled when 0 total assets."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        ws.set_total_assets(0)
        ws.set_large_images([])
        assert not ws._build_btn.isEnabled()

    def test_build_enabled_with_large_images(self, qapp):
        """Build button is enabled when large images present."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        ws.set_total_assets(5)
        ws.set_large_images(["fake/large.jpg"])
        assert ws._build_btn.isEnabled()

    def test_normal_mode_label_shown(self, qapp):
        """Normal mode label is shown when assets present but no large images."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        ws = PreprocessWorkspace()
        ws.set_total_assets(5)
        ws.set_large_images([])
        label_text = ws._large_image_label.text()
        assert "正常图片" in label_text or "Normal" in label_text
