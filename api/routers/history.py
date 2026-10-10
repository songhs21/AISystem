# api/routers/history.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.image.preference import (
    get_all_generations, get_generation_by_id,
    get_feedbacks_by_ids, save_feedback,
    update_tag_weights, get_tag_weights_bulk,
    get_top_tags_by_category, get_inpaintings_by_generation,
)
from core.image.tag import tag_meta, sync_unregistered_tags
from config.PATH import TAG_META_PATH
from config.constants import PASS_REASON_KO

router = APIRouter(prefix="/api/history", tags=["history"])


# ── 스키마 ────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    generation_id: int
    score: int | None = None
    liked_tags: list[str] = []
    disliked_tags: list[str] = []
    pass_type: str | None = None
    pass_reasons: list[str] = []
    false_tags: list[str] = []


class TagWeightsRequest(BaseModel):
    tags: list[str]


class TopTagsRequest(BaseModel):
    category: str
    limit: int = 10


# ── 엔드포인트 ────────────────────────────────────────────

@router.get("/generations")
def list_generations():
    return {"generations": get_all_generations()}


@router.get("/generations/{gen_id}")
def get_generation(gen_id: int):
    gen = get_generation_by_id(gen_id)
    if not gen:
        raise HTTPException(status_code=404, detail="generation not found")
    return gen


@router.post("/feedbacks")
def bulk_feedbacks(body: dict):
    """gen_ids 목록으로 피드백 bulk 조회"""
    gen_ids = body.get("gen_ids", [])
    return get_feedbacks_by_ids(gen_ids)


@router.post("/feedback")
def post_feedback(req: FeedbackRequest):
    unknown = [r for r in req.pass_reasons if r not in PASS_REASON_KO]
    if unknown:
        raise HTTPException(status_code=422, detail=f"알 수 없는 사유: {', '.join(unknown)}")

    if req.pass_type == "dislike":
        # 마음에 들지 않음: 태그/점수는 저장하지 않고 사유만 저장
        liked, disliked, false_tags, score, reasons = [], [], [], None, req.pass_reasons
    else:
        liked, disliked, false_tags, score, reasons = (
            req.liked_tags, req.disliked_tags, req.false_tags, req.score, [],
        )

    save_feedback(req.generation_id, score, liked, disliked, req.pass_type, reasons, false_tags)
    if req.pass_type != "dislike" and score is not None:
        update_tag_weights(liked, disliked, score)
    return {"ok": True}


@router.post("/tag-weights")
def tag_weights(req: TagWeightsRequest):
    return get_tag_weights_bulk(req.tags)


@router.post("/top-tags")
def top_tags(req: TopTagsRequest):
    return get_top_tags_by_category(tag_meta, req.category, req.limit)


@router.get("/inpaintings/{gen_id}")
def inpaintings(gen_id: int):
    return {"inpaintings": get_inpaintings_by_generation(gen_id)}


@router.post("/sync-tags")
def sync_tags():
    added = sync_unregistered_tags(TAG_META_PATH, tag_meta)
    return {"added": added}

@router.get("/all-tag-weights")
def all_tag_weights():
    from core.image.preference import get_all_tag_weights
    return get_all_tag_weights()