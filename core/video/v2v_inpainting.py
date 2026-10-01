# core/video/v2v_inpainting.py

import os
import sys
import json
import time
import uuid
import copy
import shutil
import subprocess
import requests
import websocket
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch
import torchvision
from PIL import Image as PILImage
from transformers import pipeline
from datetime import datetime
import re

sys.path.insert(0, r"D:\Python\AISystem\01-test\GroundingDINO")

from groundingdino.util.inference import load_model, predict
from groundingdino.datasets import transforms as T
from segment_anything import sam_model_registry, SamPredictor

from config.PATH import (
    COMFY_URL, COMFY_WS, COMFY_OUTPUT, COMFY_INPUT, FFMPEG_PATH
)
from core.image.generate import _post_workflow, _ws_progress


# ============================================================
# 경로 설정
# ============================================================

BASE_DIR    = Path(r"D:\Python\AISystem\01-test")
INPUT_VIDEO = BASE_DIR / "AnimateDiff_00003.mp4"
FRAMES_DIR  = BASE_DIR / "frames"
OUTPUT_DIR  = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_PATH   = BASE_DIR / "models" / "anime_seg" / "birefnext-aniseg-int8-v0.1.onnx"
GDINO_CONFIG = BASE_DIR / "models" / "groundingdino" / "GroundingDINO_SwinT_OGC.py"
GDINO_CKPT   = BASE_DIR / "models" / "groundingdino" / "groundingdino_swint_ogc.pth"
SAM_CKPT     = BASE_DIR / "models" / "sam" / "sam_vit_h_4b8939.pth"

WF_PATH = Path(r"D:\Python\AISystem\assets\workflow\inpaint_detail_workflow.json")

IPA_MODEL         = "ip-adapter_sdxl_vit-h.safetensors"
CLIP_VISION_MODEL = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"

# ============================================================
# 인페인팅 설정
# ============================================================

PART_PROMPTS = {
    "dress": "wedding dress, white dress, lace, frills, bare chest, open front dress, :3",
    "face":  "anime face, purple eyes, detailed face",
    "hand":  "detailed hand, fingers",
    "arm":   "detailed arm",
}
INPAINT_NEGATIVE = "lowres, bad anatomy, worst quality, fabric in center, center strap, center cloth, center panel"
INPAINT_DENOISE  = 0.2
IPA_WEIGHT       = 0.8
INPAINT_SEED     = 42

PART_CONFIG = {
    "dress": {"multimask": False, "min_area": 5000},
    "hand":  {"multimask": True,  "min_area": 500},
    "arm":   {"multimask": True,  "min_area": 500},
    "face":  {"multimask": False, "min_area": 3000},
}

DETECTION_CONFIG = {
    "dress": {"prompt": "white dress", "box_thresh": 0.25, "text_thresh": 0.25, "nms_iou": 0.5},
    "hand":  {"prompt": "hand",        "box_thresh": 0.25, "text_thresh": 0.25, "nms_iou": 0.3},
    "arm":   {"prompt": "arm",         "box_thresh": 0.25, "text_thresh": 0.25, "nms_iou": 0.3},
    "face":  {"prompt": "face",        "box_thresh": 0.25, "text_thresh": 0.25, "nms_iou": 0.5},
}

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ============================================================
# 모델 로드
# ============================================================

def load_detection_models():
    print("BiRefNet 로드 중...")
    birefnet_session = ort.InferenceSession(
        str(MODEL_PATH),
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )

    print("GroundingDINO 로드 중...")
    gdino = load_model(str(GDINO_CONFIG), str(GDINO_CKPT))

    print("SAM 로드 중...")
    sam = sam_model_registry["vit_h"](checkpoint=str(SAM_CKPT))
    sam.to("cuda")
    predictor = SamPredictor(sam)

    # depth_estimator = pipeline(
    #     "depth-estimation",
    #     model="depth-anything/Depth-Anything-V2-Small-hf",
    #     device="cpu",
    # )

    gdino_transform = T.Compose([
        T.RandomResize([800], max_size=1333),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    print("모델 로드 완료\n")
    return birefnet_session, gdino, predictor, sam, gdino_transform


def unload_detection_models(birefnet_session, gdino, predictor, sam):
    del birefnet_session, gdino, predictor, sam
    torch.cuda.empty_cache()
    print("감지 모델 언로드 완료")


# ============================================================
# 유틸
# ============================================================

def upload_image(path: str, name: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            f"{COMFY_URL}/upload/image",
            files={"image": (name, f, "image/png")},
            data={"overwrite": "true"},
        )
    r.raise_for_status()
    return r.json()["name"]


def extract_frames(video_path: Path, frames_dir: Path) -> float:
    frames_dir.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imwrite(str(frames_dir / f"frame_{idx:05d}.png"), frame)
        idx += 1
    cap.release()
    print(f"프레임 추출 완료: {idx}장, FPS: {fps}")
    return fps


def frames_to_video(output_dir: Path, fps: float):
    frames = sorted(output_dir.glob("comfy*.png"))
    if not frames:
        print("합칠 프레임 없음")
        return
    out_path = output_dir / "output.mp4"
    subprocess.run([
        str(FFMPEG_PATH), "-y",
        "-framerate", str(fps),
        "-i", str(output_dir / "comfy%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ], check=True)
    print(f"동영상 저장: {out_path}")


def free_comfyui_models():
    r = requests.post(
        f"{COMFY_URL}/free",
        json={"unload_models": True, "free_memory": True},
    )
    r.raise_for_status()
    print("ComfyUI 모델 언로드 완료")


# ============================================================
# BiRefNet 캐릭터 마스크
# ============================================================

def get_char_mask(frame_bgr: np.ndarray, birefnet_session) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    image_pil = PILImage.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    tw = (w // 32) * 32
    th = (h // 32) * 32
    resized = image_pil.resize((tw, th), PILImage.BILINEAR)
    arr = (np.array(resized, dtype=np.float32) / 255.0 - MEAN) / STD
    tensor = arr.transpose(2, 0, 1)[None]
    inp  = birefnet_session.get_inputs()[0]
    out  = birefnet_session.get_outputs()[0]
    result = birefnet_session.run([out.name], {inp.name: tensor})[0]
    mask = result[0, 0]
    mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    return (np.clip(mask_resized, 0, 1) * 255).astype(np.uint8)


# ============================================================
# GroundingDINO + SAM 부위별 마스크
# ============================================================

def get_part_masks(
    frame_bgr: np.ndarray,
    char_mask: np.ndarray,
    gdino,
    predictor,
    gdino_transform,
) -> dict:
    image_np  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    image_pil = PILImage.fromarray(image_np)
    image_transformed, _ = gdino_transform(image_pil, None)

    H, W = image_np.shape[:2]
    char_mask_binary = (char_mask > 127).astype(np.uint8)

    all_boxes, all_logits, all_phrases = [], [], []

    for part, cfg in DETECTION_CONFIG.items():
        p_boxes, p_logits, p_phrases = predict(
            model=gdino,
            image=image_transformed,
            caption=cfg["prompt"],
            box_threshold=cfg["box_thresh"],
            text_threshold=cfg["text_thresh"],
        )
        if len(p_boxes) == 0:
            continue

        p_xyxy = torch.stack([
            torch.tensor([
                (b[0] - b[2] / 2) * W, (b[1] - b[3] / 2) * H,
                (b[0] + b[2] / 2) * W, (b[1] + b[3] / 2) * H,
            ], dtype=torch.float32)
            for b in p_boxes
        ])
        keep = torchvision.ops.nms(p_xyxy, p_logits, cfg["nms_iou"])
        p_boxes   = p_boxes[keep]
        p_logits  = p_logits[keep]
        p_phrases = [p_phrases[i] for i in keep.tolist()]

        all_boxes.extend(p_boxes)
        all_logits.extend(p_logits)
        all_phrases.extend(p_phrases)

    if not all_boxes:
        return {}

    boxes_tensor = torch.stack(all_boxes)
    valid = [i for i, b in enumerate(boxes_tensor) if (b[2] * b[3]).item() < 0.8]
    boxes_tensor = boxes_tensor[valid]
    all_phrases  = [all_phrases[i] for i in valid]

    boxes_xyxy_list = []
    for box in boxes_tensor:
        cx, cy, bw, bh = box.tolist()
        boxes_xyxy_list.append([
            int((cx - bw / 2) * W), int((cy - bh / 2) * H),
            int((cx + bw / 2) * W), int((cy + bh / 2) * H),
        ])
    boxes_xyxy = torch.tensor(boxes_xyxy_list, dtype=torch.float32).to("cuda")

    predictor.set_image(image_np)

    masks_by_part = {key: [] for key in PART_CONFIG}
    for i, phrase in enumerate(all_phrases):
        for key in masks_by_part:
            if key in phrase:
                masks_by_part[key].append(boxes_xyxy[i])

    part_results = {}
    for part, part_boxes in masks_by_part.items():
        if not part_boxes:
            continue
        cfg     = PART_CONFIG[part]
        stacked = torch.stack(part_boxes).to("cuda")
        transformed = predictor.transform.apply_boxes_torch(stacked, image_np.shape[:2])
        part_masks, scores, _ = predictor.predict_torch(
            point_coords=None,
            point_labels=None,
            boxes=transformed,
            multimask_output=cfg["multimask"],
        )
        if cfg["multimask"]:
            best = [part_masks[i, scores[i].argmax()] for i in range(part_masks.shape[0])]
            combined = torch.stack(best).any(dim=0).cpu().numpy()
        else:
            combined = part_masks[:, 0].any(dim=0).cpu().numpy()

        combined = (combined & (char_mask_binary > 0)).astype(np.uint8) * 255

        if (combined > 127).sum() < cfg["min_area"]:
            continue

        part_results[part] = combined

    # 디버그 이미지
    debug = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    for box, phrase in zip(boxes_xyxy_list, all_phrases):
        x1, y1, x2, y2 = box
        cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(debug, phrase, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    detected_parts = "_".join(sorted(set(
        part for phrase in all_phrases for part in PART_CONFIG if part in phrase
    )))
    cv2.imwrite(str(BASE_DIR / f"debug_{detected_parts or 'none'}.png"), debug)

    return part_results


# ============================================================
# 깊이맵
# ============================================================

# def get_depth_map(frame_bgr: np.ndarray, depth_estimator) -> np.ndarray:
#     image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
#     image_pil = PILImage.fromarray(image_rgb)
#     result = depth_estimator(image_pil)
#     depth = np.array(result["depth"])
#     depth = ((depth - depth.min()) / (depth.max() - depth.min()) * 255).astype(np.uint8)
#     return depth


# ============================================================
# 마스크 병합 (IoU 기반 Union-Find)
# ============================================================

def merge_overlapping_masks(masks: dict, iou_threshold: float = 0.3) -> list:
    parts  = list(masks.keys())
    parent = {p: p for p in parts}

    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, part_a in enumerate(parts):
        for part_b in parts[i + 1:]:
            inter = cv2.bitwise_and(masks[part_a], masks[part_b])
            uni   = cv2.bitwise_or(masks[part_a], masks[part_b])
            inter_area = (inter > 127).sum()
            union_area = (uni   > 127).sum()
            if union_area == 0:
                continue
            iou = inter_area / union_area
            print(f"  IoU {part_a} ↔ {part_b}: {iou:.3f}")
            if iou >= iou_threshold:
                union(part_a, part_b)

    groups = {}
    for part in parts:
        root = find(part)
        groups.setdefault(root, []).append(part)

    merged = []
    for group in groups.values():
        merged_mask = np.zeros_like(masks[group[0]])
        for part in group:
            merged_mask = cv2.bitwise_or(merged_mask, masks[part])
        merged.append({"mask": merged_mask, "parts": group})
        if len(group) > 1:
            print(f"  → 병합 그룹: {' + '.join(group)}")

    return merged


# ============================================================
# 인페인팅 (단일 영역)
# ============================================================

def inpaint_region(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    client_id: str,
    seed: int,
    frame_path: Path,
    parts: list,
    run_dir: Path,
    workflow_template: dict,
) -> np.ndarray:
    _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if cv2.countNonZero(binary) == 0:
        return frame_bgr

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return frame_bgr

    largest     = max(contours, key=cv2.contourArea)
    clean_binary = np.zeros_like(binary)
    cv2.drawContours(clean_binary, [largest], -1, 255, -1)

    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))
    clean_binary = cv2.morphologyEx(clean_binary, cv2.MORPH_CLOSE, kernel_close)
    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    clean_binary = cv2.morphologyEx(clean_binary, cv2.MORPH_OPEN, kernel_open)

    x, y, w, h = cv2.boundingRect(clean_binary)
    pad = 16
    cx1 = max(0, x - pad);          cy1 = max(0, y - pad)
    cx2 = min(frame_bgr.shape[1], x + w + pad)
    cy2 = min(frame_bgr.shape[0], y + h + pad)

    crop_frame = frame_bgr[cy1:cy2, cx1:cx2]
    crop_mask  = clean_binary[cy1:cy2, cx1:cx2]
    crop_h, crop_w = crop_frame.shape[:2]

    TARGET_LONG = 1024
    scale = TARGET_LONG / max(crop_h, crop_w)
    if crop_w >= crop_h:
        new_w = max(32, int(round(crop_w * scale / 32)) * 32)
        new_h = max(32, int(round(new_w * crop_h / crop_w / 32)) * 32)
    else:
        new_h = max(32, int(round(crop_h * scale / 32)) * 32)
        new_w = max(32, int(round(new_h * crop_w / crop_h / 32)) * 32)

    resized_frame = cv2.resize(crop_frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    resized_mask  = cv2.resize(crop_mask,  (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    part_name = "_".join(parts)
    tmp_origin  = str(BASE_DIR / "tmp_crop_origin.png")
    tmp_mask    = str(BASE_DIR / "tmp_crop_mask.png")
    tmp_ipa_ref = str(BASE_DIR / f"tmp_ipa_ref_{part_name}.png")

    cv2.imwrite(tmp_origin,  resized_frame)
    cv2.imwrite(tmp_mask,    resized_mask)
    cv2.imwrite(tmp_ipa_ref, resized_frame)

    origin_name  = upload_image(tmp_origin,  "tmp_crop_origin.png")
    mask_name    = upload_image(tmp_mask,    "tmp_crop_mask.png")
    ipa_ref_name = upload_image(tmp_ipa_ref, f"ipa_ref_{frame_path.stem}_{part_name}.png")

    workflow = copy.deepcopy(workflow_template)

    prompt_parts = [PART_PROMPTS[p] for p in parts if p in PART_PROMPTS]
    prompt = ", ".join(prompt_parts) + ", masterpiece, best quality"

    workflow["1"]["inputs"]["image"]   = origin_name
    workflow["22"]["inputs"]["image"]  = mask_name
    workflow["18"]["inputs"]["text"]   = prompt
    workflow["19"]["inputs"]["text"]   = INPAINT_NEGATIVE
    workflow["8"]["inputs"]["denoise"] = INPAINT_DENOISE
    workflow["8"]["inputs"]["seed"]    = seed

    workflow["30"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": IPA_MODEL}}
    workflow["31"] = {"class_type": "CLIPVisionLoader",     "inputs": {"clip_name": CLIP_VISION_MODEL}}
    workflow["33"] = {"class_type": "LoadImage",            "inputs": {"image": ipa_ref_name}}
    workflow["32"] = {
        "class_type": "IPAdapterAdvanced",
        "inputs": {
            "model": ["3", 0], "ipadapter": ["30", 0], "image": ["33", 0],
            "clip_vision": ["31", 0], "weight": IPA_WEIGHT, "weight_type": "linear",
            "combine_embeds": "concat", "start_at": 0.0, "end_at": 0.6,
            "embeds_scaling": "K+V",
        },
    }
    workflow["8"]["inputs"]["model"] = ["32", 0]

    # ── ComfyUI 전송 (websocket 진행률) ──────────────────────
    prompt_id = _post_workflow(workflow, client_id)

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    for _ in _ws_progress(ws, start_ratio=0.0, end_ratio=1.0, prompt_id=prompt_id):
        pass  # 진행률 소비 (UI 연동 시 yield로 교체)

    # ── 결과 수집 ─────────────────────────────────────────────
    history = requests.get(f"{COMFY_URL}/history/{prompt_id}").json()
    result_img = None
    if prompt_id in history:
        for node_id, out in history[prompt_id]["outputs"].items():
            if "images" in out:
                img_info   = out["images"][-1]
                result_img = cv2.imread(str(COMFY_OUTPUT / img_info["filename"]))
                cv2.imwrite(
                    str(run_dir / "ipa_ref" / f"{frame_path.stem}_{part_name}.png"),
                    result_img,
                )

    if result_img is None:
        return frame_bgr

    # ── 블렌딩 ───────────────────────────────────────────────
    result_resized = cv2.resize(result_img, (crop_w, crop_h), interpolation=cv2.INTER_LANCZOS4)
    result_full    = frame_bgr.copy()

    kernel     = np.ones((15, 15), np.uint8)
    eroded     = cv2.erode(crop_mask, kernel, iterations=1)
    blend_mask = cv2.GaussianBlur(eroded, (21, 21), 0)
    blend_3ch  = np.stack([blend_mask] * 3, axis=-1).astype(np.float32) / 255.0

    roi     = result_full[cy1:cy2, cx1:cx2].astype(np.float32)
    blended = roi * (1 - blend_3ch) + result_resized.astype(np.float32) * blend_3ch
    result_full[cy1:cy2, cx1:cx2] = blended.astype(np.uint8)

    cv2.imwrite(
        str(run_dir / "inpaint" / f"{frame_path.stem}_{part_name}.png"),
        result_full,
    )
    return result_full


# ============================================================
# 진입점
# ============================================================

def run_v2v_inpainting(
    video_path: Path = INPUT_VIDEO,
    max_frames: int  = None,
    seed: int        = INPAINT_SEED,
):
    """
    V2V 의류 교체 인페인팅 파이프라인.
    UI 연동 시 generator로 전환 가능 (inpaint_region 내 ws yield 활성화).
    """
    fps = extract_frames(video_path, FRAMES_DIR)

    frames = sorted(
        p for p in FRAMES_DIR.glob("*.png")
        if re.fullmatch(r"frame(?:_| |-)?\d+\.png", p.name, re.IGNORECASE)
    )
    if max_frames:
        frames = frames[:max_frames]

    run_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    for sub in ("mask", "ipa_ref", "inpaint", "merged"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    print(f"처리 프레임: {len(frames)}")

    # ── 패스 1: 감지 ──────────────────────────────────────────
    birefnet_session, gdino, predictor, sam, gdino_transform = load_detection_models()

    all_masks  = {}
    # all_depths = {}

    for frame_path in frames:
        frame_bgr = cv2.imread(str(frame_path))
        h, w = frame_bgr.shape[:2]
        frame_large = cv2.resize(frame_bgr, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

        char_mask_large = get_char_mask(frame_large, birefnet_session)
        part_results    = get_part_masks(frame_large, char_mask_large, gdino, predictor, gdino_transform)

        all_masks[frame_path] = {
            part: cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            for part, mask in part_results.items()
        }
        for part, mask in all_masks[frame_path].items():
            cv2.imwrite(str(run_dir / "mask" / f"{frame_path.stem}_{part}.png"), mask)

        # depth_large = get_depth_map(frame_large, depth_estimator)
        # all_depths[frame_path] = cv2.resize(depth_large, (w, h), interpolation=cv2.INTER_LINEAR)

        print(f"  {frame_path.name} 감지: {list(part_results.keys())}")

    unload_detection_models(birefnet_session, gdino, predictor, sam)

    # ── 패스 2: 인페인팅 ──────────────────────────────────────
    client_id = str(uuid.uuid4())
    out_idx   = 1

    with open(WF_PATH) as f:
        workflow_template = json.load(f)

    for frame_path, masks in all_masks.items():
        frame_bgr    = cv2.imread(str(frame_path))
        merged_masks = merge_overlapping_masks(masks, iou_threshold=0.3)

        for group in merged_masks:
            part_name = "_".join(group["parts"])
            cv2.imwrite(str(run_dir / "merged" / f"{frame_path.stem}_{part_name}.png"), group["mask"])

        result = frame_bgr.copy()
        for group in merged_masks:
            result = inpaint_region(
                result, group["mask"], client_id, seed,
                frame_path, group["parts"], run_dir, workflow_template,
            )

        cv2.imwrite(str(run_dir / f"comfy{out_idx:04d}.png"), result)
        out_idx += 1

    free_comfyui_models()
    frames_to_video(run_dir, fps)


if __name__ == "__main__":
    run_v2v_inpainting()