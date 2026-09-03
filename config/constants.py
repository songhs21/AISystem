TAG_CATEGORY_ORDER = [
    "hair_style", "front_hair_style", "hair_color", "hair_color_pattern",
    "hair_accessory", "eyes_color", "emotion", "nail",
    "body_features", "body_shape", "skin_color",
    "top_style", "bra_style", "bra_color", "underwear_style",
    "design_details", "cloth_material", "cloth_prop","outfit_costume", "outfit_general",
    "outfit_swimwear", "outfit_color",
    "bottom_style", "socks_style", "footwear_style", "footwear_color",
    "pose", "framing", "situation",
    "background", "props_accessories", "props_food",
    "props_furniture", "props_objects",
]

EXTRA_CATEGORIES = {
    "age_restriction", "cloth_color_pattern", "color_pattern",
    "cloth_theme", "Armor", "number_of_people", "coupling",
    "fetish", "etc",
}

CAT_KO = {
    "hair_style": "헤어스타일", "front_hair_style": "앞머리",
    "hair_color": "머리색", "hair_color_pattern": "머리색 패턴",
    "hair_accessory": "머리 악세사리", "eyes_color": "눈 색",
    "emotion": "표정", "nail": "네일",
    "body_features": "신체 특징", "body_shape": "체형",
    "skin_color": "피부색", "top_style": "상의",
    "bra_style": "브라 스타일", "bra_color": "브라 컬러", "underwear_style": "속옷",
    "design_details": "의상 디테일", "cloth_material": "의복 재질", "cloth_prop":"의복 요소","outfit_costume": "코스튬",
    "outfit_general": "제복/유니폼", "outfit_swimwear": "수영복",
    "outfit_color": "의상 색상", "bottom_style": "하의",
    "socks_style": "양말/스타킹", "footwear_style": "신발",
    "footwear_color": "신발 색상", "pose": "포즈",
    "framing": "구도", "situation": "상황",
    "background": "배경", "props_accessories": "악세사리",
    "props_food": "음식 소품", "props_furniture": "가구 소품",
    "props_objects": "오브젝트", "기타": "기타",
}

# 모델별 오버라이딩 설정
MODEL_RESOLUTION = {
    # 🌟 AnimagineXL V4: 전용 파라미터 프로필 내장
    "animagineXL40_v4": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.0,
        "sampler_name": "Euler a",
        "scheduler": "Automatic",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.45,
        "prefix": "masterpiece, high score"
    },
    
    # 🌟 Illustrious / Noobai 계열 (SGM Uniform 최적화)
    "catTowerNoobai": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.0,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4
    },
    "novaAnimeXL_ilV190": {
        "width": 1536, "height": 1536,
        "step": 30, "steps": 30,             
        "cfg": 6.5,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4,
        "prefix": "masterpiece, best quality, masterpiece composition"
    },
    "akiumPrisma_29B": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.5,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4,
        "prefix": "masterpiece, best quality, highres"
    },
    "anillustrious": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.5,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4,
        "prefix": "masterpiece, best quality, highres"
    },
    "illustriousXL": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.5,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4,
        "prefix": "masterpiece, best quality, highres, uncensored, anime style"
    },
    "waiIllustriousSDXL": {
        "width": 1024, "height": 1024,
        "step": 40, "steps": 40,
        "cfg": 5.5,
        "sampler_name": "Euler a",
        "scheduler": "SGM Uniform",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.4,
        "prefix": "masterpiece, best quality, highres"
    },

    # 🌟 Pony 계열 (DPM++ 2M + Karras)
    "5moonPonyAsian_v10": {
        "width": 832, "height": 1216,
        "step": 30, "steps": 30,
        "cfg": 6.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.35,
        "prefix": "score_9, score_8_up, score_7_up, source_anime"
    },
    "aetherFaeSemi": {
        "width": 832, "height": 1216,
        "step": 40, "steps": 40,
        "cfg": 6.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.35,
        "prefix": "score_9, score_8_up, score_7_up, source_anime"
    },
    "prefectiousXLNSFW": {
        "width": 832, "height": 1216,
        "step": 40, "steps": 40,
        "cfg": 6.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.35,
        "prefix": "score_9, score_8_up, score_7_up"
    },

    # 🌟 SD 1.5 애니메이션 계열
    "counterfeitV30": {
        "width": 512, "height": 768,
        "step": 25, "steps": 25,
        "cfg": 7.5,
        "sampler_name": "DDIM",
        "scheduler": "Automatic",
        "hires_upscaler": "R-ESRGAN 4x+ Anime6B",
        "hires_upscale_by": 1.5,
        "hires_steps": 12,
        "hires_denoising_strength": 0.55
    },
    "abyssorangemix2SFW": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "Euler a",
        "scheduler": "Automatic",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.5
    },
    "anything45Inpainting": {
        "width": 512, "height": 512,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "DDIM",
        "scheduler": "Automatic",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.5
    },
    "anythingV3": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.5,
        "sampler_name": "Euler a",
        "scheduler": "Automatic",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.5
    },
    "meinapastel": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "Euler a",
        "scheduler": "Automatic",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.5
    },

    # 🌟 SD 1.5 실사 / 반실사 계열 (DPM++ 2M + Karras)
    "Agent_Kalashnikov10": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.45
    },
    "beretMixReal": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 6.5,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.4
    },
    "moodyProMix": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.45
    },
    "oneObsession": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.4
    },
    "unnamedixlRealisticModel": {
        "width": 832, "height": 1216, # SDXL 실사
        "step": 40, "steps": 40,
        "cfg": 5.5,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 1.5,
        "hires_steps": 15,
        "hires_denoising_strength": 0.35
    },
    "xeroxrealmix": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 6.5,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.4
    },
    "zyntoonSemiRealistic": {
        "width": 512, "height": 768,
        "step": 40, "steps": 40,
        "cfg": 7.0,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "hires_upscaler": "4x-UltraSharp",
        "hires_upscale_by": 2.0,
        "hires_steps": 20,
        "hires_denoising_strength": 0.45
    }
}


BLACKLIST = {
    'watermark',
    'signature', 
    'english_text',
    'text',
    'simple_background',
    'white_background',
    'black_background',
    'grey_background',
    'gradient_background',
    'blurry',
    'jpeg_artifacts',
    'compression_artifacts',
    'lowres'
}

PASS_REASON_KO = {
    "eye": "눈",
    "ear": "귀",
    "nose": "코",
    "mouth": "입",
    "face_overall": "얼굴 전체",
    "hand": "손",
    "finger": "손가락",
    "arm": "팔",
    "leg": "다리",
    "foot": "발",
    "body_overall": "체형/비율",
    "body_penetration": "신체 관통",
    "extra_limb": "팔다리 추가 생성",
    "clothing_fit": "의상 맞음새",
    "background": "배경",
}

NEGATIVE_BASE = "small_breasts, 1boy, shota, loli, text, watermark, clone, signature, multiple_views, username, lowres, bad anatomy, bad hands, extra digits, missing fingers, extra fingers, mutated hands, extra limbs, extra limbs, cloned face, gross proportions, malformed limbs, worst quality, low quality, jpeg artifacts, blurry, deformed, disfigured, explicit, nsfw"