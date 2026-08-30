# api/routers/inpaint.py
import os
import json
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form
from typing import Annotated
from fastapi.responses import StreamingResponse
from PIL import Image as PILImage, ImageFilter, ImageEnhance
from config.PATH import COMFY_INPUT, COMFY_OUTPUT
from config.constants import NEGATIVE_BASE
from core.image.generate import run_inpaint
from core.image.preference import get_generation_by_id, save_inpainting

router = APIRouter(prefix="/api/inpaint", tags=["inpaint"])


@router.post("/run")
async def run_inpaint_endpoint(
    gen_id:     Annotated[str,   Form()],
    mode:       Annotated[str,   Form()],
    prompt:     Annotated[str,   Form()] = "",
    negative:   Annotated[str,   Form()] = "",
    denoise:    Annotated[float, Form()] = 0.45,
    steps:      Annotated[int,   Form()] = 35,
    checkpoint: Annotated[str,   Form()] = "",
    image:      UploadFile = File(...),
    mask:       UploadFile = File(...),
):
    """
    인페인팅 실행 — SSE 스트림
    event: progress → {"value": float, "text": str}
    event: done     → {"image_path": str, "filename": str}
    event: error    → {"message": str}
    """
    # 업로드 파일 임시 저장
    image_bytes = await image.read()
    mask_bytes  = await mask.read()

    origin_path = os.path.join(COMFY_INPUT, f"inpaint_origin_{gen_id}.png")
    mask_path   = os.path.join(COMFY_INPUT, f"inpaint_mask_{gen_id}.png")

    with open(origin_path, "wb") as f:
        f.write(image_bytes)
    with open(mask_path, "wb") as f:
        f.write(mask_bytes)

    # gen 메타 로드
    gen        = get_generation_by_id(int(gen_id))
    ckpt       = checkpoint or (gen["checkpoint"] if gen else "animagineXL40_v4Opt.safetensors")
    final_neg  = negative or NEGATIVE_BASE
    final_prompt = prompt or (gen["prompt"] if gen else "")
    inpaint_mode = "detail" if mode == "detail" else "replace"

    def stream():
        try:
            output_path = None
            for event in run_inpaint(
                origin_path, mask_path, ckpt,
                final_prompt, final_neg,
                float(denoise), int(steps), inpaint_mode, int(gen_id)
            ):
                if event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    output_path = event["image_path"]

            if output_path and os.path.exists(output_path):
                filename = os.path.basename(output_path)
                save_inpainting(int(gen_id), filename)
                yield f"event: done\ndata: {json.dumps({'image_path': output_path, 'filename': filename})}\n\n"
            else:
                yield f"event: error\ndata: {json.dumps({'message': '인페인팅 결과 없음'})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        finally:
            for tmp in [origin_path, mask_path]:
                try:
                    os.remove(tmp)
                except:
                    pass

    return StreamingResponse(stream(), media_type="text/event-stream")
