# worker.py
import requests
import time
import glob
import os
import logging
import database
from tagger import analyze
from config.PATH import COMFY_URL, COMFY_OUTPUT, WORKER_LOG

logging.basicConfig(
    filename=str(WORKER_LOG),
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)


# prompt_id가 ComfyUI 큐(실행 중 / 대기 중)에 존재하는지 확인
def is_prompt_in_queue(prompt_id):
    try:
        queue_data = requests.get(f"{COMFY_URL}/queue", timeout=3).json()

        # 실행 중 / 대기 중 항목 순서로 확인
        if any(item[1] == prompt_id for item in queue_data.get("queue_running", [])):
            return True
        if any(item[1] == prompt_id for item in queue_data.get("queue_pending", [])):
            return True

        return False

    except Exception as e:
        logging.error(f"큐 확인 에러: {e}")
        return False


# ComfyUI 생성 완료를 폴링으로 감지 → 이미지 태깅 후 DB 저장
# 좀비 판정: 히스토리/큐 모두 없는 상태가 ZOMBIE_LIMIT초 지속 시 종료
# 연결 오류: CONN_ERR_LIMIT초 누적 시 강제 종료
def watch_comfy(prompt_id, before, prompt_text, seed, checkpoint):
    logging.info(f"워커 시작: prompt_id={prompt_id}")

    ZOMBIE_LIMIT   = 10
    CONN_ERR_LIMIT = 60

    zombie_streak  = 0
    conn_err_total = 0

    try:
        while True:
            time.sleep(1)

            # 서버 연결 시도 / 실패 누적
            try:
                res = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=3)
                conn_err_total = 0
            except requests.exceptions.ConnectionError:
                conn_err_total += 1
                logging.warning(f"서버 연결 실패 누적 {conn_err_total}초: prompt_id={prompt_id}")
                if conn_err_total >= CONN_ERR_LIMIT:
                    logging.error(f"서버 {CONN_ERR_LIMIT}초 다운 → 워커 강제 종료: prompt_id={prompt_id}")
                    return
                continue

            # 히스토리에서 완료 확인 → 이미지 탐색 + 태깅 + DB 저장
            history = res.json()
            if prompt_id in history:
                logging.info(f"완료 확인: prompt_id={prompt_id}")
                time.sleep(0.5)

                files = glob.glob(os.path.join(str(COMFY_OUTPUT), "*.png"))
                new_files = [f for f in files if os.path.getctime(f) > before]

                if new_files:
                    image_path = max(new_files, key=os.path.getctime)
                    tags = [{"tag": t["tag"], "score": t["score"]} for t in analyze(image_path)]
                    gen_id = database.save_generation_complete(
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
                return

            # 큐 생존 확인 → 좀비 카운터 리셋
            if is_prompt_in_queue(prompt_id):
                zombie_streak  = 0
                conn_err_total = 0
                continue

            # 히스토리/큐 모두 없음 → 좀비 의심 카운트 (연결 정상일 때만)
            if conn_err_total == 0:
                zombie_streak += 1
                logging.warning(f"좀비 의심 {zombie_streak}/{ZOMBIE_LIMIT}: prompt_id={prompt_id}")
            if zombie_streak >= ZOMBIE_LIMIT:
                logging.error(f"좀비 확정 → DB 등록 없이 종료: prompt_id={prompt_id}")
                return

    except Exception as e:
        logging.error(f"워커 치명적 에러: prompt_id={prompt_id}, error={e}")