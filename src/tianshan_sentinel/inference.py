from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(slots=True)
class Prediction:
    probability: np.ndarray
    uncertainty: np.ndarray
    engine: str
    threshold: float


@dataclass(slots=True)
class RegistrationResult:
    image: np.ndarray
    comparable: bool
    aligned: bool
    reason: str
    match_count: int = 0
    inlier_count: int = 0
    inlier_ratio: float = 0.0
    feature_coverage: float = 0.0
    area_ratio: float = 0.0


def _registration_view(image: np.ndarray, max_dimension: int = 1280) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(height, width))
    if scale == 1.0:
        return image, scale
    resized = cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _is_pre_registered(before_gray: np.ndarray, after_gray: np.ndarray) -> bool:
    """Recognize dataset-style pairs whose pixels already share one coordinate grid."""
    height, width = before_gray.shape
    window = cv2.createHanningWindow((width, height), cv2.CV_32F)
    shift, response = cv2.phaseCorrelate(
        before_gray.astype(np.float32),
        after_gray.astype(np.float32),
        window,
    )
    shift_limit = max(4.0, min(height, width) * 0.05) if height == width else 1.5
    return bool(
        np.isfinite(shift).all()
        and np.isfinite(response)
        and abs(shift[0]) <= shift_limit
        and abs(shift[1]) <= shift_limit
        and response >= 0.06
    )


def register_after_to_before(before_rgb: np.ndarray, after_rgb: np.ndarray) -> RegistrationResult:
    """Validate scene correspondence before applying a conservative ORB homography."""
    before_height, before_width = before_rgb.shape[:2]
    after_height, after_width = after_rgb.shape[:2]
    before_ratio = before_width / max(before_height, 1)
    after_ratio = after_width / max(after_height, 1)
    ratio_delta = abs(np.log(max(before_ratio, 1e-6) / max(after_ratio, 1e-6)))
    if ratio_delta > 0.08:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "两张影像的宽高比差异过大，无法建立可靠的同一区域对应关系。",
        )

    if after_rgb.shape[:2] != before_rgb.shape[:2]:
        after_rgb = cv2.resize(
            after_rgb,
            (before_width, before_height),
            interpolation=cv2.INTER_LINEAR,
        )

    before_view, scale = _registration_view(before_rgb)
    after_view, _ = _registration_view(after_rgb)
    before_gray = cv2.cvtColor(before_view, cv2.COLOR_RGB2GRAY)
    after_gray = cv2.cvtColor(after_view, cv2.COLOR_RGB2GRAY)
    if _is_pre_registered(before_gray, after_gray):
        return RegistrationResult(
            after_rgb,
            True,
            False,
            "影像已处于配准状态，无需二次几何变换。",
        )

    detector = cv2.ORB_create(nfeatures=2500, fastThreshold=12)
    keypoints_before, descriptors_before = detector.detectAndCompute(before_gray, None)
    keypoints_after, descriptors_after = detector.detectAndCompute(after_gray, None)
    if descriptors_before is None or descriptors_after is None:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "影像中的稳定特征不足，无法确认两张图是否来自同一区域。",
        )

    candidates = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(
        descriptors_after,
        descriptors_before,
        k=2,
    )
    matches = []
    for pair in candidates:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance < 0.75 * second.distance:
            matches.append(best)
    if len(matches) < 20:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "两张影像没有足够的共同特征，可能并非同一区域或拍摄视角差异过大。",
            match_count=len(matches),
        )

    source = np.float32([keypoints_after[match.queryIdx].pt for match in matches]).reshape(-1, 1, 2)
    destination = np.float32([keypoints_before[match.trainIdx].pt for match in matches]).reshape(-1, 1, 2)
    matrix, inliers = cv2.findHomography(source, destination, cv2.RANSAC, 4.0)
    if matrix is None or inliers is None:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "共同特征无法形成稳定的几何关系，影像不可比较。",
            match_count=len(matches),
        )

    inlier_mask = inliers.ravel().astype(bool)
    inlier_count = int(inlier_mask.sum())
    inlier_ratio = inlier_count / len(matches)
    if inlier_count < 15 or inlier_ratio < 0.25:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "共同特征的一致性过低，无法可靠配准两张影像。",
            match_count=len(matches),
            inlier_count=inlier_count,
            inlier_ratio=round(inlier_ratio, 4),
        )

    projected_inliers = cv2.perspectiveTransform(source[inlier_mask], matrix)
    reprojection_errors = np.linalg.norm(
        projected_inliers - destination[inlier_mask],
        axis=2,
    ).ravel()
    if float(np.median(reprojection_errors)) > 4.0:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "配准重投影误差过大，无法生成可信的变化结果。",
            match_count=len(matches),
            inlier_count=inlier_count,
            inlier_ratio=round(inlier_ratio, 4),
        )

    view_height, view_width = before_view.shape[:2]
    view_area = float(view_height * view_width)
    source_hull = cv2.convexHull(source[inlier_mask].reshape(-1, 2))
    destination_hull = cv2.convexHull(destination[inlier_mask].reshape(-1, 2))
    feature_coverage = min(
        abs(cv2.contourArea(source_hull)),
        abs(cv2.contourArea(destination_hull)),
    ) / view_area

    corners = np.float32(
        [[[0, 0]], [[view_width - 1, 0]], [[view_width - 1, view_height - 1]], [[0, view_height - 1]]]
    )
    projected_corners = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
    area_ratio = abs(cv2.contourArea(projected_corners.astype(np.float32))) / view_area
    finite_geometry = np.isfinite(projected_corners).all()
    convex_geometry = finite_geometry and cv2.isContourConvex(projected_corners.astype(np.float32))
    margin_x, margin_y = view_width * 0.35, view_height * 0.35
    within_bounds = finite_geometry and bool(
        np.all(projected_corners[:, 0] >= -margin_x)
        and np.all(projected_corners[:, 0] <= view_width - 1 + margin_x)
        and np.all(projected_corners[:, 1] >= -margin_y)
        and np.all(projected_corners[:, 1] <= view_height - 1 + margin_y)
    )
    if feature_coverage < 0.01 or not convex_geometry or not within_bounds or not 0.5 <= area_ratio <= 2.0:
        return RegistrationResult(
            after_rgb,
            False,
            False,
            "配准变换存在过度拉伸、翻转或特征过度集中，已拒绝生成误导性结果。",
            match_count=len(matches),
            inlier_count=inlier_count,
            inlier_ratio=round(inlier_ratio, 4),
            feature_coverage=round(feature_coverage, 4),
            area_ratio=round(area_ratio, 4),
        )

    if scale != 1.0:
        scaling = np.array([[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]])
        matrix = np.linalg.inv(scaling) @ matrix @ scaling
    aligned = cv2.warpPerspective(
        after_rgb,
        matrix,
        (before_width, before_height),
        borderMode=cv2.BORDER_REFLECT,
    )
    return RegistrationResult(
        aligned,
        True,
        True,
        "配准质量通过。",
        match_count=len(matches),
        inlier_count=inlier_count,
        inlier_ratio=round(inlier_ratio, 4),
        feature_coverage=round(feature_coverage, 4),
        area_ratio=round(area_ratio, 4),
    )


def align_after_to_before(before_rgb: np.ndarray, after_rgb: np.ndarray) -> tuple[np.ndarray, bool]:
    """Backward-compatible alignment helper; invalid pairs fail closed without warping."""
    registration = register_after_to_before(before_rgb, after_rgb)
    return registration.image, registration.aligned


class HeuristicPredictor:
    """Out-of-box baseline for UI demos; it is explicitly not a trained model."""

    engine_name = "opencv-heuristic-demo"

    def predict(self, before_rgb: np.ndarray, after_rgb: np.ndarray) -> Prediction:
        before_lab = cv2.cvtColor(before_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        after_lab = cv2.cvtColor(after_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        difference = np.linalg.norm(after_lab - before_lab, axis=2)
        difference = cv2.GaussianBlur(difference, (7, 7), 0)
        low, high = np.percentile(difference, [20, 99])
        probability = np.clip((difference - low) / max(high - low, 1e-6), 0.0, 1.0)
        probability = cv2.morphologyEx(probability, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        uncertainty = 1.0 - np.abs(probability - 0.5) * 2.0
        return Prediction(probability, uncertainty, self.engine_name, 0.55)


def _structural_change_evidence(before_rgb: np.ndarray, after_rgb: np.ndarray) -> np.ndarray:
    """Measure local structural change while reducing sensitivity to illumination shifts."""
    before_gray = cv2.cvtColor(before_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    after_gray = cv2.cvtColor(after_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0

    def local_statistics(image: np.ndarray, size: int = 31) -> tuple[np.ndarray, np.ndarray]:
        mean = cv2.boxFilter(image, -1, (size, size), borderType=cv2.BORDER_REFLECT)
        square_mean = cv2.boxFilter(image * image, -1, (size, size), borderType=cv2.BORDER_REFLECT)
        deviation = np.sqrt(np.maximum(square_mean - mean * mean, 1e-4))
        return mean, deviation

    before_mean, before_deviation = local_statistics(before_gray)
    after_mean, after_deviation = local_statistics(after_gray)
    before_normalized = np.clip((before_gray - before_mean) / before_deviation, -3.0, 3.0)
    after_normalized = np.clip((after_gray - after_mean) / after_deviation, -3.0, 3.0)
    normalized_difference = cv2.GaussianBlur(
        np.abs(before_normalized - after_normalized) / 6.0,
        (9, 9),
        0,
    )

    before_mu = cv2.GaussianBlur(before_gray, (21, 21), 3)
    after_mu = cv2.GaussianBlur(after_gray, (21, 21), 3)
    before_variance = cv2.GaussianBlur(before_gray * before_gray, (21, 21), 3) - before_mu * before_mu
    after_variance = cv2.GaussianBlur(after_gray * after_gray, (21, 21), 3) - after_mu * after_mu
    covariance = cv2.GaussianBlur(before_gray * after_gray, (21, 21), 3) - before_mu * after_mu
    structural_similarity = (
        (2.0 * before_mu * after_mu + 0.01**2) * (2.0 * covariance + 0.03**2)
    ) / (
        (before_mu * before_mu + after_mu * after_mu + 0.01**2)
        * (before_variance + after_variance + 0.03**2)
        + 1e-8
    )
    structural_difference = cv2.GaussianBlur(
        np.clip((1.0 - structural_similarity) / 2.0, 0.0, 1.0),
        (9, 9),
        0,
    )

    before_edges = cv2.Canny(np.uint8(before_gray * 255.0), 50, 130)
    after_edges = cv2.Canny(np.uint8(after_gray * 255.0), 50, 130)
    before_edge_density = cv2.GaussianBlur((before_edges > 0).astype(np.float32), (0, 0), 5)
    after_edge_density = cv2.GaussianBlur((after_edges > 0).astype(np.float32), (0, 0), 5)
    edge_difference = np.clip(np.abs(before_edge_density - after_edge_density) * 8.0, 0.0, 1.0)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    before_equalized = clahe.apply(np.uint8(before_gray * 255.0)).astype(np.float32) / 255.0
    after_equalized = clahe.apply(np.uint8(after_gray * 255.0)).astype(np.float32) / 255.0
    appearance_difference = cv2.GaussianBlur(
        np.abs(before_equalized - after_equalized),
        (9, 9),
        0,
    )

    evidence = (
        0.32 * normalized_difference
        + 0.38 * structural_difference
        + 0.20 * edge_difference
        + 0.10 * appearance_difference
    )
    return cv2.GaussianBlur(np.clip(evidence, 0.0, 1.0), (11, 11), 0)


def _fuse_seeded_structural_change(
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
    probability: np.ndarray,
    uncertainty: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Expand sparse model detections only through connected structural evidence."""
    total_pixels = probability.size
    seed = (probability >= threshold).astype(np.uint8)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    seed_count, _, seed_stats, seed_centroids = cv2.connectedComponentsWithStats(seed, connectivity=8)
    minimum_seed_area = max(9, round(total_pixels * 0.00002))
    centroids = [
        (int(round(seed_centroids[index, 0])), int(round(seed_centroids[index, 1])))
        for index in range(1, seed_count)
        if seed_stats[index, cv2.CC_STAT_AREA] >= minimum_seed_area
    ]
    if not centroids:
        return probability, uncertainty, False

    evidence = _structural_change_evidence(before_rgb, after_rgb)
    candidate = (evidence >= 0.34).astype(np.uint8)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((5, 5), dtype=np.uint8))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((13, 13), dtype=np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    accepted = np.zeros_like(candidate)
    minimum_component_area = max(40, round(total_pixels * 0.0001))
    proximity_radius = max(5, round(min(probability.shape) * 0.02))
    proximity_kernel = np.ones((proximity_radius * 2 + 1, proximity_radius * 2 + 1), dtype=np.uint8)

    for label_id in range(1, component_count):
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area < minimum_component_area:
            continue
        component = (labels == label_id).astype(np.uint8)
        nearby = cv2.dilate(component, proximity_kernel)
        seed_hits = sum(
            0 <= x < nearby.shape[1] and 0 <= y < nearby.shape[0] and bool(nearby[y, x])
            for x, y in centroids
        )
        required_hits = 2 if area / total_pixels >= 0.02 else 1
        if seed_hits >= required_hits:
            accepted[component > 0] = 1

    if not accepted.any():
        return probability, uncertainty, False

    structural_probability = threshold + 0.02 + np.clip(
        (evidence - 0.34) / 0.66,
        0.0,
        1.0,
    ) * (0.98 - threshold)
    accepted_mask = accepted > 0
    added_mask = accepted_mask & (probability < threshold)
    fused_probability = probability.copy()
    fused_probability[accepted_mask] = np.maximum(
        fused_probability[accepted_mask],
        structural_probability[accepted_mask],
    )
    fused_uncertainty = uncertainty.copy()
    fused_uncertainty[added_mask] = np.maximum(
        fused_uncertainty[added_mask],
        np.clip((1.0 - evidence[added_mask]) * 0.5, 0.0, 0.5),
    )
    return fused_probability, fused_uncertainty, bool(added_mask.any())


def _sliding_positions(length: int, tile_size: int, overlap: float = 0.25) -> list[int]:
    if length <= tile_size:
        return [0]
    stride = max(1, round(tile_size * (1.0 - overlap)))
    positions = list(range(0, length - tile_size + 1, stride))
    final_position = length - tile_size
    if positions[-1] != final_position:
        positions.append(final_position)
    return positions


def _square_tile(image: np.ndarray, x: int, y: int, tile_size: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    height, width = image.shape[:2]
    content_height = min(tile_size, height - y)
    content_width = min(tile_size, width - x)
    tile = image[y : y + content_height, x : x + content_width]
    padding_height = tile_size - content_height
    padding_width = tile_size - content_width
    padding_top = padding_height // 2
    padding_left = padding_width // 2
    if padding_height or padding_width:
        border_mode = cv2.BORDER_REFLECT_101 if min(tile.shape[:2]) > 1 else cv2.BORDER_REPLICATE
        tile = cv2.copyMakeBorder(
            tile,
            padding_top,
            padding_height - padding_top,
            padding_left,
            padding_width - padding_left,
            border_mode,
        )
    crop = (padding_left, padding_top, content_width, content_height)
    return tile, crop


class TiledBidirectionalPredictor:
    """Run learned change detectors without stretching a full-resolution scene."""

    image_size: int
    threshold: float
    engine_name: str
    batch_tiles = 8

    def _tensor_batch(self, images: list[np.ndarray]) -> np.ndarray:
        tensors = []
        for image in images:
            resized = cv2.resize(
                np.ascontiguousarray(image),
                (self.image_size, self.image_size),
                interpolation=cv2.INTER_LINEAR,
            )
            normalized = (resized.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
            tensors.append(normalized.transpose(2, 0, 1))
        return np.ascontiguousarray(np.stack(tensors), dtype=np.float32)

    def _tensor(self, image: np.ndarray) -> np.ndarray:
        return self._tensor_batch([image])

    def _run_batch(self, before_images: list[np.ndarray], after_images: list[np.ndarray]) -> np.ndarray:
        raise NotImplementedError

    def _predict_scale(
        self,
        before_rgb: np.ndarray,
        after_rgb: np.ndarray,
        tile_size: int,
        probability: np.ndarray,
        uncertainty: np.ndarray,
    ) -> None:
        height, width = before_rgb.shape[:2]
        coordinates = [
            (x, y)
            for y in _sliding_positions(height, tile_size)
            for x in _sliding_positions(width, tile_size)
        ]
        for start in range(0, len(coordinates), self.batch_tiles):
            chunk = coordinates[start : start + self.batch_tiles]
            before_tiles = []
            after_tiles = []
            crops = []
            for x, y in chunk:
                before_tile, crop = _square_tile(before_rgb, x, y, tile_size)
                after_tile, _ = _square_tile(after_rgb, x, y, tile_size)
                before_tiles.append(before_tile)
                after_tiles.append(after_tile)
                crops.append(crop)

            # Temporal max fusion makes construction and demolition equivalent even
            # when a trained attention gate has learned an ordering preference.
            outputs = self._run_batch(
                before_tiles + after_tiles,
                after_tiles + before_tiles,
            )
            forward = outputs[: len(chunk)]
            reverse = outputs[len(chunk) :]
            for index, (x, y) in enumerate(chunk):
                tile_probability = np.maximum(forward[index], reverse[index])
                tile_uncertainty = np.abs(forward[index] - reverse[index])
                if tile_probability.shape != (tile_size, tile_size):
                    tile_probability = cv2.resize(
                        tile_probability,
                        (tile_size, tile_size),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    tile_uncertainty = cv2.resize(
                        tile_uncertainty,
                        (tile_size, tile_size),
                        interpolation=cv2.INTER_LINEAR,
                    )

                crop_x, crop_y, crop_width, crop_height = crops[index]
                tile_probability = tile_probability[
                    crop_y : crop_y + crop_height,
                    crop_x : crop_x + crop_width,
                ]
                tile_uncertainty = tile_uncertainty[
                    crop_y : crop_y + crop_height,
                    crop_x : crop_x + crop_width,
                ]
                probability_view = probability[y : y + crop_height, x : x + crop_width]
                uncertainty_view = uncertainty[y : y + crop_height, x : x + crop_width]
                replace = tile_probability > probability_view
                np.copyto(probability_view, tile_probability, where=replace)
                np.copyto(uncertainty_view, tile_uncertainty, where=replace)

    def predict(self, before_rgb: np.ndarray, after_rgb: np.ndarray) -> Prediction:
        if before_rgb.shape != after_rgb.shape:
            raise ValueError("Registered image pairs must have identical shapes")
        height, width = before_rgb.shape[:2]
        probability = np.zeros((height, width), dtype=np.float32)
        uncertainty = np.zeros((height, width), dtype=np.float32)
        tile_sizes = [self.image_size]
        context_size = round(self.image_size * 1.5)
        if min(height, width) >= context_size:
            tile_sizes.append(context_size)
        for tile_size in tile_sizes:
            self._predict_scale(before_rgb, after_rgb, tile_size, probability, uncertainty)
        structural_fusion = False
        if min(height, width) > self.image_size:
            probability, uncertainty, structural_fusion = _fuse_seeded_structural_change(
                before_rgb,
                after_rgb,
                probability,
                uncertainty,
                self.threshold,
            )
        engine = f"{self.engine_name}+structural-fusion" if structural_fusion else self.engine_name
        return Prediction(probability, uncertainty, engine, self.threshold)


class OnnxPredictor(TiledBidirectionalPredictor):
    engine_name = "onnxruntime-siamese-resnet18"

    def __init__(self, model_path: str | Path, image_size: int | None = None, threshold: float | None = None):
        import onnxruntime as ort

        model_path = Path(model_path)
        metadata_path = model_path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.image_size = int(image_size if image_size is not None else metadata.get("image_size", 256))
        self.threshold = float(threshold if threshold is not None else metadata.get("threshold", 0.5))

    def _run_batch(self, before_images: list[np.ndarray], after_images: list[np.ndarray]) -> np.ndarray:
        logits = self.session.run(
            None,
            {"before": self._tensor_batch(before_images), "after": self._tensor_batch(after_images)},
        )[0][:, 0]
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -80.0, 80.0)))


class TorchPredictor(TiledBidirectionalPredictor):
    engine_name = "pytorch-siamese-resnet18"

    def __init__(self, checkpoint_path: str | Path, image_size: int = 256):
        import torch

        from .model import load_model_from_checkpoint

        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model, self.metadata = load_model_from_checkpoint(str(checkpoint_path), self.device)
        self.image_size = image_size
        self.threshold = self.metadata["threshold"]

    def _run_batch(self, before_images: list[np.ndarray], after_images: list[np.ndarray]) -> np.ndarray:
        before_tensor = self.torch.from_numpy(self._tensor_batch(before_images)).to(self.device)
        after_tensor = self.torch.from_numpy(self._tensor_batch(after_images)).to(self.device)
        with self.torch.no_grad():
            logits = self.model(before_tensor, after_tensor) / self.metadata["temperature"]
            return self.torch.sigmoid(logits)[:, 0].cpu().numpy()


def load_rgb(path: str | Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))
