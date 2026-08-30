# core/system/watcher.py
import requests
import time
import glob
import os
import logging
from config.PATH import COMFY_URL, COMFY_OUTPUT, WORKER_LOG
from core.image.tag import analyze
from core.image.preference import save_generation_complete

logging.basicConfig(
    filename=str(WORKER_LOG),
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

def is_prompt_in_queue(prompt_id: str) -> bool:
    try:
        queue_data = requests.get(f"{COMFY_URL}/queue", timeout=3).json()
        if any(item[1] == prompt_id for item in queue_data.get("queue_running", [])):
            return True
        if any(item[1] == prompt_id for item in queue_data.get("queue_pending", [])):
            return True
        return False
    except Exception as e:
        logging.error(f"큐 확인 에러: {e}")
        return False


def watch_comfy(prompt_id: str, before: float, prompt_text: str,
                seed: int, checkpoint: str, pre_gen_id: int = None):
    logging.info(f"워커 시작: prompt_id={prompt_id}")

    ZOMBIE_LIMIT   = 10
    CONN_ERR_LIMIT = 60
    zombie_streak  = 0
    conn_err_total = 0

    try:
        while True:
            time.sleep(1)

            try:
                res = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=3)
                conn_err_total = 0
            except requests.exceptions.ConnectionError:
                conn_err_total += 1
                logging.warning(f"서버 연결 실패 누적 {conn_err_total}초: prompt_id={prompt_id}")
                if conn_err_total >= CONN_ERR_LIMIT:
                    logging.error(f"서버 {CONN_ERR_LIMIT}초 다운 → 워커 강제 종료")
                    return
                continue

            history = res.json()
            if prompt_id in history:
                logging.info(f"완료 확인: prompt_id={prompt_id}")
                time.sleep(0.5)

                files = glob.glob(os.path.join(str(COMFY_OUTPUT), "*.png"))
                new_files = [f for f in files if os.path.getctime(f) > before]  # ← 여기서 정의

                if new_files:
                    image_path = max(new_files, key=os.path.getctime)
                    tags = [{"tag": t["tag"], "score": t["score"]} for t in analyze(image_path)]
                    logging.info(f"태그 수: {len(tags)}, 샘플: {tags[:3]}")
                    gen_id = save_generation_complete(
                        gen_id=pre_gen_id,
                        prompt_id=prompt_id,
                        prompt_text=prompt_text,
                        seed=seed,
                        checkpoint=checkpoint,
                        image_path=image_path,
                        tags=tags,
                    )
                    logging.info(f"DB 저장 완료: gen_id={gen_id}")
                else:
                    logging.error(f"이미지 파일 유실: prompt_id={prompt_id}")
                return  # ← 이게 if new_files 블록 바깥, if prompt_id in history 블록 안에 있어야 함

            if is_prompt_in_queue(prompt_id):
                zombie_streak  = 0
                conn_err_total = 0
                continue

            if conn_err_total == 0:
                zombie_streak += 1
                logging.warning(f"좀비 의심 {zombie_streak}/{ZOMBIE_LIMIT}: prompt_id={prompt_id}")
            if zombie_streak >= ZOMBIE_LIMIT:
                logging.error(f"좀비 확정 → DB 등록 없이 종료: prompt_id={prompt_id}")
                return

    except Exception as e:
        logging.error(f"워커 치명적 에러: prompt_id={prompt_id}, error={e}")
