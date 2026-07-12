# tagger.py
import onnxruntime as ort
import csv
import numpy as np
from PIL import Image
from config.PATH import MODEL_PATH, MODEL_TAG_PATH
from config.constants import BLACKLIST


# selected_tags.csv에서 태그 이름 목록 로드
def load_tags():
    with open(MODEL_TAG_PATH, encoding="utf-8") as f:
        return [row["name"] for row in csv.DictReader(f)]


# WD14 모델 입력 형식에 맞게 전처리 (448x448 리사이즈, RGB→BGR, 배치 차원 추가)
def preprocess_image(image_path):
    image = Image.open(image_path).convert("RGB")
    image = np.array(image.resize((448, 448)), dtype=np.float32)
    image = image[:, :, ::-1]
    return np.expand_dims(image, axis=0)


# 모듈 임포트 시 1회 로드 (세션 / 태그 목록)
session    = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
tags       = load_tags()


# 이미지 태깅 실행 → 블랙리스트 제외 + threshold 필터링 후 score 내림차순 반환
def analyze(image_path, threshold=0.25, top_k=50):
    outputs = session.run(None, {input_name: preprocess_image(image_path)})[0][0]

    results = [
        {"tag": tags[i], "score": float(score)}
        for i, score in enumerate(outputs)
        if tags[i].lower() not in BLACKLIST and score >= threshold
    ]

    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


if __name__ == "__main__":
    for r in analyze(r"C:\AI\ComfyUI_windows_portable\ComfyUI\output\test.png"):
        print(r)