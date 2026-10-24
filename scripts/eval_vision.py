import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools import analyze_image

TARGET_CLASSES = {
    "pothole": "pothole",
    "plain_road": "unclear",
    "garbage": "garbage",
    "non_garbage": "unclear",
    "streetlight": "streetlight",
    "waterlogging": "waterlogging"
}

def evaluate_vision(eval_dir: Path) -> None:
    print("=" * 65)
    print(" civic Complaint Agent - Gemini Zero-Shot Vision Evaluation ")
    print("=" * 65)
    
    if not eval_dir.exists():
        print(f"Directory {eval_dir} does not exist.")
        print("Skipping all categories. No images evaluated.")
        print(f"Evaluated classes: None. Skipped classes: {', '.join(TARGET_CLASSES.keys())}")
        print("\nDefault recommendation: Confidence threshold = 0.70 (baseline)")
        return

    results = []
    skipped_classes = []
    evaluated_classes = []

    for folder_name, expected_issue in TARGET_CLASSES.items():
        class_folder = eval_dir / folder_name
        if not class_folder.exists() or not class_folder.is_dir():
            skipped_classes.append(folder_name)
            continue

        image_files = [
            f for f in class_folder.iterdir()
            if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
        ]
        
        if not image_files:
            skipped_classes.append(folder_name)
            continue
            
        evaluated_classes.append(folder_name)
        sample = image_files[:15]
        print(f"\nEvaluating '{folder_name}' ({len(sample)} images, expected issue: '{expected_issue}')...")

        for img_path in sample:
            try:
                with open(img_path, "rb") as f:
                    img_bytes = f.read()
                
                prediction = analyze_image(img_bytes)
                pred_issue = prediction.get("issue", "unclear")
                confidence = float(prediction.get("confidence", 0.0))
                
                is_correct = (pred_issue == expected_issue)
                results.append({
                    "path": str(img_path),
                    "class_folder": folder_name,
                    "expected": expected_issue,
                    "predicted": pred_issue,
                    "confidence": confidence,
                    "is_correct": is_correct
                })
                print(f"  [{'✓' if is_correct else '✗'}] {img_path.name}: pred={pred_issue} (conf={confidence:.2f})")
                
                # Respect rate limit (Gemini free tier)
                time.sleep(1.5)
            except Exception as e:
                print(f"  Error evaluating {img_path.name}: {e}")

    print("\n" + "=" * 65)
    print("EVALUATION SUMMARY")
    print("=" * 65)
    
    if skipped_classes:
        print(f"ℹ️ Skipped (no data found): {', '.join(skipped_classes)}")
    if evaluated_classes:
        print(f"✅ Evaluated: {', '.join(evaluated_classes)}")
    else:
        print("No evaluation images were available to process.")
        print("Recommended confidence threshold: 0.70 (default domain standard)")
        return

    # Per-class accuracy
    class_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        c = r["class_folder"]
        class_stats[c]["total"] += 1
        if r["is_correct"]:
            class_stats[c]["correct"] += 1

    print("\n--- Per-Class Accuracy ---")
    for c, stats in class_stats.items():
        acc = (stats["correct"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        print(f"  {c:<15}: {stats['correct']}/{stats['total']} ({acc:.1f}%)")

    # Correct vs incorrect confidence
    correct_confs = [r["confidence"] for r in results if r["is_correct"]]
    incorrect_confs = [r["confidence"] for r in results if not r["is_correct"]]

    avg_correct_conf = (sum(correct_confs) / len(correct_confs)) if correct_confs else 0.0
    avg_incorrect_conf = (sum(incorrect_confs) / len(incorrect_confs)) if incorrect_confs else 0.0

    print("\n--- Confidence Analysis ---")
    print(f"  Avg confidence for correct predictions:   {avg_correct_conf:.2f}")
    print(f"  Avg confidence for incorrect predictions: {avg_incorrect_conf:.2f}")

    # Confusion Matrix
    unique_expected = sorted(list(set(r["expected"] for r in results)))
    unique_pred = sorted(list(set(r["predicted"] for r in results)))
    all_labels = sorted(list(set(unique_expected + unique_pred)))

    cm = defaultdict(lambda: defaultdict(int))
    for r in results:
        cm[r["expected"]][r["predicted"]] += 1

    print("\n--- Confusion Matrix ---")
    corner_title = "Expected / Pred"
    header = f"{corner_title:<22}" + "".join(f"{lbl:<14}" for lbl in all_labels)
    print(header)
    print("-" * len(header))

    for exp in all_labels:
        row = f"{exp:<22}" + "".join(f"{cm[exp][pred]:<14}" for pred in all_labels)
        print(row)

    # Threshold Recommendation
    # Select threshold separating correct positive predictions from incorrect
    best_thresh = 0.70
    if correct_confs and incorrect_confs:
        # Candidate thresholds between 0.5 and 0.9
        candidates = [round(x * 0.05, 2) for x in range(10, 19)]
        best_f1 = -1.0
        for t in candidates:
            tp = sum(1 for c in correct_confs if c >= t)
            fp = sum(1 for c in incorrect_confs if c >= t)
            fn = sum(1 for c in correct_confs if c < t)
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = t
    elif correct_confs:
        best_thresh = max(0.65, min(0.85, round(avg_correct_conf * 0.85, 2)))

    print("\n" + "=" * 65)
    print(f"🎯 RECOMMENDED CONFIDENCE THRESHOLD: {best_thresh:.2f}")
    print("=" * 65)


if __name__ == "__main__":
    eval_folder = PROJECT_ROOT / "data" / "eval"
    evaluate_vision(eval_folder)
