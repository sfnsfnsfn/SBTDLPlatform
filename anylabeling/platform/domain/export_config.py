"""Export domain contracts — pure dataclass DTOs with no UI or framework imports.

For Phase 4, the only supported export format is ONNX.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportTarget:
    """Export target environment profile.

    Attributes:
        id: Unique target identifier (e.g. "onnx_generic", "windows_cpu").
        display_name: Human-readable name.
        format: Export format (always "onnx" for Phase 4).
        description: One-line description of the target.
    """

    id: str
    display_name: str
    format: str = "onnx"
    description: str = ""


@dataclass(frozen=True)
class CompatibilityResult:
    """Single compatibility check result.

    Attributes:
        name: Check name (e.g. "task_support", "weight_integrity").
        passed: Whether the check passed.
        detail: Human-readable detail message.
        fix_action: Optional action label to fix the issue
            (e.g. "重新训练").
    """

    name: str
    passed: bool
    detail: str = ""
    fix_action: str = ""


@dataclass(frozen=True)
class SelfTestReport:
    """ONNX self-test validation report.

    Attributes:
        passed: Whether all samples passed the deviation check.
        samples_tested: Number of samples tested.
        max_deviation: Maximum relative deviation observed.
        failures: List of failure descriptions (sample index +
            deviation).
        created_at: When the report was generated.
    """

    passed: bool
    samples_tested: int = 0
    max_deviation: float = 0.0
    failures: tuple[str, ...] = ()
    created_at: str = ""


# Predefined export targets (Phase 4: ONNX only)
EXPORT_TARGETS: tuple[ExportTarget, ...] = (
    ExportTarget(
        id="onnx_generic",
        display_name="通用 ONNX",
        description="标准 ONNX 格式，适用于大多数部署环境",
    ),
    ExportTarget(
        id="windows_cpu",
        display_name="Windows CPU (ONNX Runtime)",
        description="Windows CPU 推理，使用 ONNX Runtime",
    ),
    ExportTarget(
        id="platform_prelabel",
        display_name="本平台预标注模型",
        description="注册为本地预标注模型，供标注工作区使用",
    ),
    ExportTarget(
        id="custom",
        display_name="自定义",
        description="自定义导出参数",
    ),
)


# PRD §7.10 delivery package structure (10 items)
DEPLOY_PACKAGE_FILES: tuple[tuple[str, str], ...] = (
    ("model.onnx", "ONNX 模型文件"),
    ("labels.json", "类别映射文件"),
    ("preprocess.json", "预处理参数"),
    ("postprocess.json", "后处理参数"),
    ("model_manifest.json", "模型清单"),
    ("checksum.sha256", "完整性校验文件"),
    ("validation_report.json", "自测验证报告"),
    ("sample/input.png", "示例输入图像"),
    ("sample/output.png", "示例输出图像"),
    ("README_部署说明.md", "部署说明文档"),
)

__all__ = [
    "CompatibilityResult",
    "DEPLOY_PACKAGE_FILES",
    "ExportTarget",
    "EXPORT_TARGETS",
    "SelfTestReport",
]
