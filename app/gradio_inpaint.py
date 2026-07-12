# gradio_inpaint.py
import gradio as gr
import sys
import os
import json
import subprocess
import time
import numpy as np
from PIL import Image as PILImage, ImageFilter, ImageEnhance

sys.path.append(r"D:\Python\AISystem\PreferenceMemory")

import database
from comfyApi import run_inpaint
from config.constants import NEGATIVE_BASE
from config.PATH import GRADIO_START_LOG, INPAINT_REQUEST, COMFY_INPUT, COMFY_OUTPUT, CHECKPOINT_DIR


# 로컬 체크포인트 파일 목록 조회
def get_local_checkpoints():
    if not os.path.exists(CHECKPOINT_DIR):
        return []
    return sorted([f for f in os.listdir(CHECKPOINT_DIR) if f.endswith(('.safetensors', '.ckpt'))])


# inpaint_request.json에서 gen_id / image_path 로드 후 Gradio 초기값 반환
def load_image_from_request():
    try:
        with open(INPAINT_REQUEST) as f:
            data = json.load(f)

        gen_id = str(data["gen_id"])
        image_path = data["image_path"]

        if os.path.exists(image_path):
            img = PILImage.open(image_path).convert("RGB")
            gen = database.get_generation_by_id(int(gen_id))
            prompt = gen["prompt"] if gen else ""
            return img, prompt, gen_id

    except Exception as e:
        print(f"load_image_from_request 에러: {e}")

    return None, "", "0"


# 레이어별 마스크 추출 → 크롭 → 인페인팅 → 블렌딩 순차 처리
# 모든 레이어 완료 후 최종 블렌딩 이미지를 output 폴더에 저장 및 DB 등록
def inpaint(image_and_mask, prompt, negative, denoise, steps, mode, checkpoint_override, gen_id):
    if image_and_mask is None:
        return None, "마스크를 먼저 그려주세요."

    background = image_and_mask.get("background")
    layers = image_and_mask.get("layers", [])

    if background is None or not layers:
        return None, "마스크를 먼저 그려주세요."

    inpaint_mode = "replace" if mode == "영역 교체 (복장/배경)" else "detail"

    # 생성 메타데이터 로드 / 체크포인트·프롬프트 기본값 처리
    gen = database.get_generation_by_id(int(gen_id))
    checkpoint = checkpoint_override if checkpoint_override else (gen["checkpoint"] if gen else "")
    if not checkpoint or checkpoint == "Unknown":
        checkpoint = "animagineXL40_v4Opt.safetensors"
    if not prompt.strip():
        prompt = gen["prompt"] if gen else ""
    if not negative.strip():
        negative = NEGATIVE_BASE

    current_image = background.astype(np.uint8)
    final_output_path = None


    for idx, layer in enumerate(layers):
        # 마스크 알파 채널 추출 (RGBA → alpha, RGB → any)
        mask_layer = layer.astype(np.uint8)
        if mask_layer.shape[2] == 4:
            mask_alpha = (mask_layer[:, :, 3] > 127).astype(np.uint8) * 255
        else:
            mask_alpha = np.any(mask_layer > 0, axis=2).astype(np.uint8) * 255

        if mask_alpha.max() == 0:
            continue

        # 마스크 BBox 계산 + 20px 패딩 적용
        rows = np.any(mask_alpha > 0, axis=1)
        cols = np.any(mask_alpha > 0, axis=0)
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]

        pad = 20
        h, w = current_image.shape[:2]
        rmin = max(0, rmin - pad)
        rmax = min(h, rmax + pad)
        cmin = max(0, cmin - pad)
        cmax = min(w, cmax + pad)

        # BBox 기준 크롭
        cropped_image = current_image[rmin:rmax, cmin:cmax]
        cropped_mask  = mask_alpha[rmin:rmax, cmin:cmax]
        crop_h, crop_w = cropped_image.shape[:2]

        # 장변 기준 512px 리사이즈
        scale = 512 / max(crop_w, crop_h)
        resized_w = int(crop_w * scale)
        resized_h = int(crop_h * scale)

        resized_image = PILImage.fromarray(cropped_image).resize((resized_w, resized_h), PILImage.LANCZOS)

        # 임시 파일 저장 (origin / mask → ComfyUI input 폴더)
        origin_path = os.path.join(COMFY_INPUT, f"inpaint_origin_{gen_id}_layer{idx}.png")
        mask_path   = os.path.join(COMFY_INPUT, f"inpaint_mask_{gen_id}_layer{idx}.png")

        resized_image.convert("RGB").save(origin_path)

        mask_rgba = (
            PILImage.fromarray(cropped_mask)
            .resize((resized_w, resized_h), PILImage.NEAREST)
            .convert("L")
            .convert("RGB")
        )
        mask_rgba.save(mask_path)
        assert os.path.exists(mask_path), f"마스크 저장 실패: {repr(mask_path)}"

        # 인페인팅 실행
        output_path = None
        for event in run_inpaint(origin_path, mask_path, checkpoint, prompt, negative, float(denoise), int(steps), inpaint_mode):
            if event["type"] == "done":
                output_path = event["image_path"]

        # 임시 파일 정리
        for tmp_file in [origin_path, mask_path]:
            try:
                os.remove(tmp_file)
            except:
                pass

        if not output_path or not os.path.exists(output_path):
            return None, f"레이어 {idx+1} 인페인팅 실패"

        # 인페인팅 결과를 원본 크롭 크기로 다운스케일 후 원본 이미지에 블렌딩
        inpainted_crop = PILImage.open(output_path).convert("RGB").resize((crop_w, crop_h), PILImage.LANCZOS)

        base = PILImage.fromarray(current_image)
        mask_for_blend = PILImage.fromarray(cropped_mask).resize((crop_w, crop_h), PILImage.LANCZOS).convert("L")

        # 가우시안 블러 + 대비 강화로 경계 페더링
        mask_feathered = ImageFilter.GaussianBlur(radius=4)
        mask_feathered = ImageEnhance.Contrast(mask_for_blend.filter(mask_feathered)).enhance(2.5)

        base.paste(inpainted_crop, (cmin, rmin), mask_feathered)
        current_image = np.array(base)

        final_output_path = output_path


    if not final_output_path:
        return None, "처리할 마스크가 없습니다."

    # 최종 블렌딩 이미지 저장 및 DB 등록
    final_blend_filename = os.path.basename(final_output_path).replace(".png", "_blend.png")
    final_blend_path = os.path.join(str(COMFY_OUTPUT), final_blend_filename)

    PILImage.fromarray(current_image).save(final_blend_path)

    try:
        os.remove(final_output_path)
    except:
        pass

    database.save_inpainting(int(gen_id), final_blend_filename)
    return PILImage.fromarray(current_image), f"완료 ({len(layers)}개 레이어 처리)"


# Gradio UI 구성 및 이벤트 바인딩
def launch_inpaint_ui():
    with gr.Blocks(title="인페인팅") as demo:
        gr.Markdown("## 🖌️ 인페인팅")

        gen_id_state = gr.State("0")

        with gr.Row():
            with gr.Column():
                image_input = gr.ImageEditor(
                    label="마스크 영역 지정",
                    brush=gr.Brush(colors=["#ff0000"], color_mode="fixed"),
                    height=700,
                )
                mode_radio = gr.Radio(
                    choices=["영역 교체 (복장/배경)", "디테일 수정 (눈/손)"],
                    value="영역 교체 (복장/배경)",
                    label="인페인팅 모드"
                )
                checkpoint_dropdown = gr.Dropdown(
                    choices=get_local_checkpoints(),
                    label="체크포인트 (비우면 원본 사용)",
                    value=None
                )
                prompt_input  = gr.Textbox(label="프롬프트 (비우면 원본 사용)")
                negative_input = gr.Textbox(label="네거티브 (비우면 기본값 사용)")

                with gr.Row():
                    denoise_slider = gr.Slider(0.1, 1.0, value=0.45, label="Denoise 강도")
                    steps_slider   = gr.Slider(10, 60, value=35, step=1, label="Steps")

                run_btn = gr.Button("✅ 인페인팅 시작", variant="primary")

            with gr.Column():
                output_image = gr.Image(label="결과")
                status_text  = gr.Textbox(label="상태")

        # 초기 이미지 / 프롬프트 로드
        demo.load(load_image_from_request, inputs=None, outputs=[image_input, prompt_input, gen_id_state])

        # 인페인팅 실행 버튼 바인딩
        run_btn.click(
            inpaint,
            inputs=[image_input, prompt_input, negative_input, denoise_slider, steps_slider, mode_radio, checkpoint_dropdown, gen_id_state],
            outputs=[output_image, status_text]
        )

    return demo


if __name__ == "__main__":
    demo = launch_inpaint_ui()

    # 포트 7860으로 실행 / 점유 시 기존 프로세스 킬 후 재시도
    try:
        demo.launch(server_port=7860, inbrowser=False)
    except OSError:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if ":7860" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                break
        time.sleep(1)
        demo.launch(server_port=7860, inbrowser=False)