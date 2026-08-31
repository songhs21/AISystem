# api/routers/history.py
from fastapi import APIRouter
from pydantic import BaseModel
from core.image.preference import (
    get_all_generations, get_generation_by_id,
    get_feedbacks_by_ids, save_feedback,
    update_tag_weights, get_tag_weights_bulk,
    get_top_tags_by_category, get_inpaintings_by_generation,
)
from core.image.tag import tag_meta, sync_unregistered_tags
from config.PATH import TAG_META_PATH

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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="generation not found")
    return gen


@router.post("/feedbacks")
def bulk_feedbacks(body: dict):
    """gen_ids 목록으로 피드백 bulk 조회"""
    gen_ids = body.get("gen_ids", [])
    return get_feedbacks_by_ids(gen_ids)


@router.post("/feedback")
def post_feedback(req: FeedbackRequest):
    save_feedback(
        req.generation_id, req.score,
        req.liked_tags, req.disliked_tags,
        req.pass_type, req.pass_reasons, req.false_tags
    )
    if req.pass_type != "dislike" and req.score is not None:
        update_tag_weights(req.liked_tags, req.disliked_tags, req.score)
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