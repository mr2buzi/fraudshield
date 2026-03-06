from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


def choose_alert_threshold(y_true, probabilities, min_precision: float = 0.7) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    best_threshold = 0.65
    best_recall = -1.0
    for current_precision, current_recall, threshold in zip(precision[:-1], recall[:-1], thresholds):
        if current_precision >= min_precision and current_recall > best_recall:
            best_recall = current_recall
            best_threshold = float(threshold)
    return round(best_threshold, 4)


def summarize_metrics(y_true, probabilities, threshold: float) -> dict[str, float]:
    predictions = (probabilities >= threshold).astype(int)
    true_positive = int(np.sum((predictions == 1) & (y_true == 1)))
    predicted_positive = int(np.sum(predictions == 1))
    actual_positive = int(np.sum(y_true == 1))
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / actual_positive if actual_positive else 0.0
    return {
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 4),
        "precision_at_alert": round(float(precision), 4),
        "recall_at_alert": round(float(recall), 4),
    }
