"""MisclassificationService — identifies model error cases for review.

Analyzes confusion matrices, predictions, and annotations to surface:
- False positives (predicted but not annotated)
- False negatives (annotated but not predicted)
- Low-confidence predictions

Used by EvaluateWorkspace to populate the misclassification review panel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from anylabeling.platform.domain.annotation import AnnotationObject
    from anylabeling.platform.domain.prediction import PredictionObject


class MisclassificationService:
    """Detects model error patterns from validation output.

    Usage::

        svc = MisclassificationService()
        fps = svc.get_false_positives(confusion_matrix, class_names, preds, 0.5)
        fns = svc.get_false_negatives(confusion_matrix, class_names, annotations)
        low_conf = svc.get_low_confidence(preds, 0.25)
    """

    # ------------------------------------------------------------------
    # False positives
    # ------------------------------------------------------------------

    def get_false_positives(
        self,
        confusion_matrix: np.ndarray | None,
        class_names: list[str],
        predictions: list[PredictionObject],
        conf_threshold: float = 0.5,
    ) -> list[PredictionObject]:
        """Identify false positive predictions.

        A false positive is a prediction that was made (with confidence
        above *conf_threshold*) but that corresponds to a cell in the
        confusion matrix where the predicted class does not match the
        true class (off-diagonal elements).

        If the confusion matrix is not available, returns predictions
        below the confidence threshold as a heuristic estimate.

        Args:
            confusion_matrix: NxN numpy confusion matrix, or None.
            class_names: Ordered class name list matching matrix rows/cols.
            predictions: All prediction objects from validation.
            conf_threshold: Minimum confidence to consider (default 0.5).

        Returns:
            Predictions likely to be false positives.
        """
        if not predictions:
            return []

        if confusion_matrix is None or not isinstance(confusion_matrix, np.ndarray):
            # Heuristic: low-confidence preds are likely errors
            return [p for p in predictions if p.score < conf_threshold]

        n_classes = confusion_matrix.shape[0]

        # Off-diagonal entries represent misclassifications.
        # For each predicted class j, off-diagonal element (i, j) where i != j
        # represents a false positive (predicted j, truth is i).
        fp_indices: set[int] = set()
        for j in range(n_classes):  # predicted class
            for i in range(n_classes):  # true class
                if i != j and confusion_matrix[i, j] > 0:
                    fp_indices.add(j)

        if not fp_indices:
            return []

        # Return predictions whose label_id is in fp_indices
        return [p for p in predictions if p.label_id in fp_indices]

    # ------------------------------------------------------------------
    # False negatives
    # ------------------------------------------------------------------

    def get_false_negatives(
        self,
        confusion_matrix: np.ndarray | None,
        class_names: list[str],
        annotations: list[AnnotationObject],
    ) -> list[AnnotationObject]:
        """Identify false negative annotations (ground truth not predicted).

        A false negative is a ground-truth annotation whose class was
        missed by the model.  In the confusion matrix, row i contains
        the counts for true class i; the sum of off-diagonal entries
        in row i represents false negatives for class i.

        If the confusion matrix is not available, returns an empty list.

        Args:
            confusion_matrix: NxN numpy confusion matrix, or None.
            class_names: Ordered class name list matching matrix rows/cols.
            annotations: All ground-truth annotation objects.

        Returns:
            Annotation objects likely to have been missed (false negatives).
        """
        if not annotations:
            return []

        if confusion_matrix is None or not isinstance(confusion_matrix, np.ndarray):
            return []

        n_classes = confusion_matrix.shape[0]

        # For each true class i, off-diagonal sum > 0 means there are FN
        fn_classes: set[int] = set()
        for i in range(n_classes):  # true class
            off_diag_sum = 0
            for j in range(n_classes):  # predicted class
                if i != j:
                    off_diag_sum += confusion_matrix[i, j]
            if off_diag_sum > 0:
                fn_classes.add(i)

        if not fn_classes:
            return []

        return [a for a in annotations if a.label_id in fn_classes]

    # ------------------------------------------------------------------
    # Low confidence
    # ------------------------------------------------------------------

    def get_low_confidence(
        self,
        predictions: list[PredictionObject],
        conf_threshold: float = 0.25,
    ) -> list[PredictionObject]:
        """Return predictions with confidence below *conf_threshold*.

        These are predictions the model is uncertain about and may
        warrant manual review.

        Args:
            predictions: All prediction objects.
            conf_threshold: Score threshold (default 0.25).

        Returns:
            Predictions with score < conf_threshold.
        """
        if not predictions:
            return []
        return [p for p in predictions if p.score < conf_threshold]

    # ------------------------------------------------------------------
    # Confused samples
    # ------------------------------------------------------------------

    def get_confused_pairs(
        self,
        confusion_matrix: np.ndarray | None,
        class_names: list[str],
        top_k: int = 5,
    ) -> list[dict]:
        """Return the most-confused class pairs from the confusion matrix.

        Args:
            confusion_matrix: NxN confusion matrix.
            class_names: Ordered class names.
            top_k: Number of top confused pairs to return.

        Returns:
            List of dicts with keys: true_class, pred_class, true_idx,
            pred_idx, count.
        """
        if confusion_matrix is None or not isinstance(confusion_matrix, np.ndarray):
            return []

        n_classes = confusion_matrix.shape[0]
        pairs: list[dict] = []
        for i in range(n_classes):
            for j in range(n_classes):
                if i != j and confusion_matrix[i, j] > 0:
                    pairs.append({
                        "true_class": (
                            class_names[i] if i < len(class_names) else f"class_{i}"
                        ),
                        "pred_class": (
                            class_names[j] if j < len(class_names) else f"class_{j}"
                        ),
                        "true_idx": i,
                        "pred_idx": j,
                        "count": int(confusion_matrix[i, j]),
                    })

        pairs.sort(key=lambda x: x["count"], reverse=True)
        return pairs[:top_k]


__all__ = ["MisclassificationService"]
