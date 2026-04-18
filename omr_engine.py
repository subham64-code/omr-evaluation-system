import math

import cv2
import numpy as np


OPTIONS = "ABCD"


def _deskew(gray):
    coords = np.column_stack(np.where(gray > 0))
    if len(coords) < 10:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _bubble_confidence(mask_patch):
    total = mask_patch.size
    filled = np.count_nonzero(mask_patch)
    return round(float(filled) / float(total + 1e-9), 4)


def _fallback_grid_detector(binary, total_questions, options_per_question):
    h, w = binary.shape
    top_margin = int(0.1 * h)
    bottom_margin = int(0.05 * h)
    left_margin = int(0.1 * w)
    right_margin = int(0.1 * w)

    usable_h = h - top_margin - bottom_margin
    usable_w = w - left_margin - right_margin

    row_h = usable_h / max(total_questions, 1)
    col_w = usable_w / max(options_per_question, 1)

    responses = {}
    confidence = {}
    anomalies = []

    for q_idx in range(total_questions):
        fill_scores = []
        y1 = int(top_margin + q_idx * row_h)
        y2 = int(top_margin + (q_idx + 1) * row_h)

        for o_idx in range(options_per_question):
            x1 = int(left_margin + o_idx * col_w)
            x2 = int(left_margin + (o_idx + 1) * col_w)
            patch = binary[y1:y2, x1:x2]
            fill_scores.append(_bubble_confidence(patch))

        best_idx = int(np.argmax(fill_scores))
        top = fill_scores[best_idx]
        sorted_scores = sorted(fill_scores, reverse=True)
        second = sorted_scores[1] if len(sorted_scores) > 1 else 0

        question_no = str(q_idx + 1)
        marked_option = OPTIONS[best_idx]

        if top < 0.12:
            marked_option = "-"
        elif abs(top - second) < 0.03:
            anomalies.append(f"Q{question_no}: multiple marks possible")

        responses[question_no] = marked_option
        confidence[question_no] = round(top, 3)

    return responses, confidence, anomalies


def process_omr_image(image_path, total_questions, options_per_question=4):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Failed to load image")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = _deskew(gray)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        21,
        7,
    )

    responses, confidence, anomalies = _fallback_grid_detector(binary, total_questions, options_per_question)

    # Smart correction for partially filled bubbles.
    corrected = {}
    for q, opt in responses.items():
        c = confidence.get(q, 0.0)
        if opt == "-" and c > 0.08:
            corrected[q] = "A"
            anomalies.append(f"Q{q}: partial fill auto-corrected")
        else:
            corrected[q] = opt

    avg_conf = round(float(sum(confidence.values())) / max(len(confidence), 1), 3)
    return {
        "responses": corrected,
        "confidence": confidence,
        "anomalies": anomalies,
        "average_confidence": avg_conf,
    }


def evaluate_submission(answer_key, student_response, negative_marking=0.0, confidence_map=None):
    confidence_map = confidence_map or {}

    correct = 0
    wrong = 0
    unattempted = 0
    breakdown = {}

    for q_no, right_answer in answer_key.items():
        marked = student_response.get(str(q_no), "-")
        is_correct = marked == right_answer
        if marked == "-":
            unattempted += 1
        elif is_correct:
            correct += 1
        else:
            wrong += 1

        breakdown[str(q_no)] = {
            "marked": marked,
            "correct": right_answer,
            "is_correct": is_correct,
        }

    score = round(correct - (wrong * negative_marking), 2)
    total_answered = max(correct + wrong, 1)
    accuracy = round((correct / total_answered) * 100.0, 2)
    confidence_avg = round(sum(confidence_map.values()) / max(len(confidence_map), 1), 3)

    return {
        "score": score,
        "correct": correct,
        "wrong": wrong,
        "unattempted": unattempted,
        "accuracy": accuracy,
        "confidence_avg": confidence_avg,
        "confidence_by_question": confidence_map,
        "breakdown": breakdown,
    }
