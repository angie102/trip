# -*- coding: utf-8 -*-
"""구글이 준 업종 → 지도 마커 여섯. 조회하지 않는 순수한 표다.

한동안 「점심」 아래 후보는 밥집, 「구경」 아래 후보는 볼거리라고 물려주려 했다.
그것이 틀렸다 — 「구경」은 내가 그 시간에 무엇을 하는가이고, 마커가 말해야 하는
것은 그 자리가 무엇인가다. 완전히 다른 축이다. 실제로 「구경」 아래에는 요구르트
가게도, 젤라또집도, 온천도 섞여 있었고 넷에 하나가 거짓말을 했다.

그 자리가 무엇인지는 그 자리가 안다. 이름으로 추측하지 않는다.

    야스다 요구르트      food_store        음식점
    Un BOURBON        confectionery     과자
    Gelateria Regalo  ice_cream_shop    아이스크림 가게
    아시게자키 전망대     observation_deck  전망대

업종을 받아 오는 일은 여기 없다 — `places_lookup.py --kinds` 가 한다.
이 파일에 남은 것은 표와 kind_of() 뿐이라 화면 쪽(export_web)이 그대로
import 한다. 조회 코드가 함께 있던 때는 화면이 API 열쇠를 읽는 모듈을
끌어들이고 있었다.
"""
from __future__ import annotations

# ── 구글의 분류 마흔아홉 가지 → 마커 여섯 ─────────────────
# 여기 없는 것은 모두 place 다. 구글이 분류를 못 준 자리(로프웨이·축제·양조장)도
# 마찬가지다 — 「그 밖」이 아니라 「그냥 가는 곳」이라는 뜻이라 기본값이 맞다.
MARKER: dict[str, tuple[str, ...]] = {
    # 앉아서 밥을 먹는 곳
    "food": (
        "restaurant", "japanese_restaurant", "seafood_restaurant",
        "korean_restaurant", "japanese_izakaya_restaurant",
        "japanese_curry_restaurant", "tonkatsu_restaurant", "ramen_restaurant",
        "dim_sum_restaurant", "italian_restaurant", "bistro", "barbecue_area",
    ),
    # 앉아서 마시는 곳
    "cafe": ("cafe", "coffee_shop", "coffee_stand", "cafeteria"),
    # 사서 가지고 나오는 곳. 구글은 과자·디저트를 먹는 곳으로 묶지만
    # 메이플 매니아도 우오야도 사가는 데지 앉는 데가 아니다.
    "shopping": (
        "confectionery", "pastry_shop", "dessert_shop", "dessert_restaurant",
        "bakery", "donut_shop", "ice_cream_shop", "tea_store", "deli",
        "store", "shopping_mall", "supermarket", "grocery_store",
        "food_store", "asian_grocery_store", "toy_store",
    ),
    "onsen": ("public_bath", "spa"),
    # car_rental 은 업종이지만 우리에게는 시각을 지켜야 하는 약속이다.
    # 예약과 같은 자리에 둔다 — 지도에서 먼저 보여야 하는 것이 그것이다.
    "resv": ("car_rental",),
}
OF_TYPE = {t: k for k, ts in MARKER.items() for t in ts}


def kind_of(place: dict) -> str:
    """그 자리가 지도에서 무엇으로 보일까. 모르면 place."""
    return OF_TYPE.get(place.get("primaryType") or "", "place")
