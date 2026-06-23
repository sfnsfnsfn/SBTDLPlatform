"""DatasetViewModel -- manages Data Workspace state for tile/split parameters."""

from __future__ import annotations


class DatasetViewModel:
    """ViewModel for Data Workspace tile and split configuration."""

    DEFAULT_TILE_WIDTH = 1024
    DEFAULT_TILE_HEIGHT = 1024
    DEFAULT_OVERLAP_PERCENT = 20
    DEFAULT_SPLIT_SEED = 42
    DEFAULT_TRAIN_RATIO = 0.7
    DEFAULT_VAL_RATIO = 0.2
    DEFAULT_TEST_RATIO = 0.1

    def __init__(self):
        self._tile_width = self.DEFAULT_TILE_WIDTH
        self._tile_height = self.DEFAULT_TILE_HEIGHT
        self._overlap_percent = self.DEFAULT_OVERLAP_PERCENT
        self._split_seed = self.DEFAULT_SPLIT_SEED
        self._train_ratio = self.DEFAULT_TRAIN_RATIO
        self._val_ratio = self.DEFAULT_VAL_RATIO
        self._test_ratio = self.DEFAULT_TEST_RATIO
        self.asset_count = 0
        self.task_spec_id: str | None = None

    @property
    def tile_width(self) -> int:
        return self._tile_width

    @tile_width.setter
    def tile_width(self, value: int):
        if value <= 0:
            raise ValueError("tile_width must be > 0")
        self._tile_width = value

    @property
    def tile_height(self) -> int:
        return self._tile_height

    @tile_height.setter
    def tile_height(self, value: int):
        if value <= 0:
            raise ValueError("tile_height must be > 0")
        self._tile_height = value

    @property
    def overlap_percent(self) -> int:
        return self._overlap_percent

    @overlap_percent.setter
    def overlap_percent(self, value: int):
        if value < 0 or value >= 100:
            raise ValueError("overlap_percent must be between 0 and 99")
        self._overlap_percent = value

    @property
    def overlap_x_pixels(self) -> int:
        return int(self._tile_width * self._overlap_percent / 100)

    @property
    def overlap_y_pixels(self) -> int:
        return int(self._tile_height * self._overlap_percent / 100)

    @property
    def split_seed(self) -> int:
        return self._split_seed

    @split_seed.setter
    def split_seed(self, value: int):
        self._split_seed = value

    @property
    def train_ratio(self) -> float:
        return self._train_ratio

    @train_ratio.setter
    def train_ratio(self, value: float):
        self._train_ratio = value

    @property
    def val_ratio(self) -> float:
        return self._val_ratio

    @val_ratio.setter
    def val_ratio(self, value: float):
        self._val_ratio = value

    @property
    def test_ratio(self) -> float:
        return self._test_ratio

    @test_ratio.setter
    def test_ratio(self, value: float):
        self._test_ratio = value

    def can_build(self) -> bool:
        return self.asset_count > 0 and self.task_spec_id is not None

    def build_request(self) -> dict:
        return {
            "tile_width": self._tile_width,
            "tile_height": self._tile_height,
            "overlap_x": self.overlap_x_pixels,
            "overlap_y": self.overlap_y_pixels,
            "split_seed": self._split_seed,
            "train_ratio": self._train_ratio,
            "val_ratio": self._val_ratio,
            "test_ratio": self._test_ratio,
            "task_spec_id": self.task_spec_id,
        }
