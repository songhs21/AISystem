from pathlib import Path

# PATH
PROJECT_ROOT= Path(__file__).resolve().parent.parent
COMFY_LOOT   = Path(r"C:\AI\ComfyUI_windows_portable")
LOCAL_PYTHON = Path(r"C:\python3.10.\python.exe")
COMFY_DIR   = COMFY_LOOT/"ComfyUI"
ASSETS_DIR  = PROJECT_ROOT/"assets"
# python
GRADIO_INPAINT  = PROJECT_ROOT/"app"/"gradio_inpaint.py"
# DB
DB_PATH     = PROJECT_ROOT /"data"/"data.db"
# TAG_MODEL
MODEL_PATH     = ASSETS_DIR/"models"/"wd14"/"model.onnx"
MODEL_TAG_PATH = ASSETS_DIR/"models"/"wd14"/"selected_tags.csv"
# Comfy_UI
COMFY_URL           = "http://127.0.0.1:8188"
COMFY_WS            = "ws://127.0.0.1:8188/ws"
COMFY_OUTPUT        = COMFY_DIR/"output"
COMFY_INPUT         = COMFY_DIR/"input"
PYTHON_EMBEDED      = COMFY_LOOT/"python_embeded"/"python.exe"
CHECKPOINT_DIR      = COMFY_DIR/"models"/"checkpoints"
UPSCALE_MODEL_DIR   = COMFY_DIR/"models"/"upscale_models"
# Gradio
GRADIO_START_LOG    = PROJECT_ROOT/"data"/"logs"/"gradio_start.txt"
GRADIO_LOG          = PROJECT_ROOT/"data"/"logs"/"gradio_log.txt"
WORKER_LOG          = PROJECT_ROOT/"data"/"logs"/"worker.log"
INPAINT_REQUEST     = PROJECT_ROOT/"data"/"inpaint_request.json"
# json
WORKFLOW_PATH   = ASSETS_DIR/"workflow"/"custom_workflow_api.json"
CONFIG_PATH     = PROJECT_ROOT/"config"/"config.json"
UPSCALE_WORKFLOW_DIR     = ASSETS_DIR/"workflow"/"upscale_workflow.json"
INPAINTING_DIR  =  ASSETS_DIR/"workflow"/"inpaint_workflow.json"
DETAIL_INPAINTING_DIR =  ASSETS_DIR/"workflow"/"inpaint_detail_workflow.json"
# TAG
TAG_META_PATH = ASSETS_DIR/"tag"/"tag_meta.json"
# HAIR
HAIR_LENGTH      = ASSETS_DIR/"tag"/"hair_length.txt"
HAIR_STYLE       = ASSETS_DIR/"tag"/"hair_style.txt"
BANGS            = ASSETS_DIR/"tag"/"bangs.txt"
HAIR_DETAILS     = ASSETS_DIR/"tag"/"hair_details.txt"
HAIR_ACCESSORIES = ASSETS_DIR/"tag"/"hair_accessories.txt"
# HEAD
MOUTH_STYLE      = ASSETS_DIR/"tag"/"mouth.txt"
# Clothes
TOP_STYLE        = ASSETS_DIR/"tag"/"top_style.txt"
BOTTOM_STYLE     = ASSETS_DIR/"tag"/"bottom_style.txt"
OUTERWEAR        = ASSETS_DIR/"tag"/"outerwear.txt"
COSTUME_BASE     = ASSETS_DIR/"tag"/"costume_base.txt"
FASHION_THEME    = ASSETS_DIR/"tag"/"fashion_theme.txt"
SEASON_COSTUME   = ASSETS_DIR/"tag"/"season_costume.txt"
DESIGN_DETAILS   = ASSETS_DIR/"tag"/"design_details.txt"
MATERIAL_DETAILS = ASSETS_DIR/"tag"/"material_details.txt"
LEGWEAR          = ASSETS_DIR/"tag"/"legwear.txt"
FOOTWEAR         = ASSETS_DIR/"tag"/"footwear.txt"
# Accessories
ACCESSORIES      = ASSETS_DIR/"tag"/"accessories.txt"
# POSE
POSES_PATH       = ASSETS_DIR/"tag"/"poses.txt"
# BG
BG_PATH          = ASSETS_DIR/"tag"/"bg.txt"