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
        "width": 832, "height": 1216, 
        "steps": 28, "cfg": 5.5, 
        "prefix": "score_9, score_8_up, score_7_up, quality_high, source_anime"
    },
    # 궤도 수정 없이 기존 세팅(해상도만 제어)을 유지할 모델들
    "catTowerNoobai": {"width": 832, "height": 1216},
    "novaAnimeXL_ilV190":{
        "width": 832, "height": 1216,
        "steps": 30,             
        "cfg": 6.5,              # 💡 모델이 과도하게 타버리지 않도록 CFG를 적정 수준으로 하향
        # 💡 [핵심] 모델의 셀 채색/애니메이션 화풍을 존중하는 태그 구성
        "prefix": "masterpiece, best quality, highres, anime style, flat color, clean lineart, vibrant colors, sharp focus, masterpiece composition"
    },
    "counterfeitV30": {"width": 512, "height": 768},
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

NEGATIVE_BASE = "small_breasts, 1boy, shota, loli, text, watermark, clone, signature, multiple_views, username, lowres, bad anatomy, bad hands, extra digits, missing fingers, extra fingers, mutated hands, extra limbs, extra limbs, cloned face, gross proportions, malformed limbs, worst quality, low quality, jpeg artifacts, blurry, deformed, disfigured, explicit, nsfw"