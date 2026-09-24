"""DB'siz unit testlar."""

import time

from app.ai.context import to_llm_messages
from app.ai.masking import PhoneMasker, normalize_phone
from app.ai.prompt import build_state_note, build_system_prompt, fmt_sum
from app.api.deps import validate_init_data
from app.models import Message, Shop, ShopSettings
from app.services.catalog_import import parse_rows
from app.services.delivery import delivery_info, find_zone
from app.services.handoff import detect_script, handoff_reply_for, wants_human
from app.services.search import rrf_merge
from app.services.text import normalize
from tests.factories import BOT_TOKEN, ZONES, init_data


def test_normalize_mixes_scripts():
    assert normalize("Қора ко‘йлак") == normalize("qora ko'ylak") == "qora koylak"
    assert normalize("ПЛАТЬЕ!") == "plate"
    assert normalize("  G‘isht, 42-razmer ") == "gisht 42 razmer"


def test_phone_masking_roundtrip():
    masker = PhoneMasker()
    text = masker.mask("Raqamim +998 90 123-45-67, ikkinchisi 91 765 43 21")
    assert "[PHONE_1]" in text and "[PHONE_2]" in text and "123" not in text
    assert masker.unmask("[PHONE_1]") == "+998901234567"
    assert masker.unmask("[PHONE_2]") == "+998917654321"
    # Qayta maskalash o'sha tokenni beradi
    assert masker.mask("998901234567") == "[PHONE_1]"
    assert masker.unmask("[PHONE_9]") is None
    assert normalize_phone("12345") is None


def test_delivery_zone_by_keyword_and_location():
    assert find_zone(ZONES, "Chilonzor 9-kvartal")["name"] == "Toshkent shahri"
    assert find_zone(ZONES, "Самарқанд шаҳри")["name"] == "Viloyatlar"
    assert find_zone(ZONES, "Nukus") is None
    zones = [{"name": "Markaz", "fee": 15000, "center": [41.31, 69.28], "radius_km": 10}]
    assert find_zone(zones, location={"latitude": 41.32, "longitude": 69.25})["name"] == "Markaz"
    assert find_zone(zones, location={"latitude": 39.65, "longitude": 66.96}) is None
    info = delivery_info(ZONES, "Nukus")
    assert info["found"] is False and len(info["zones"]) == 2


def test_handoff_keywords_and_script():
    assert wants_human("Operator bilan gaplashmoqchiman")
    assert wants_human("Позовите оператора пожалуйста")
    assert wants_human("pulimni qaytarib bering")
    assert wants_human("Хочу возврат")
    assert not wants_human("Qora ko'ylak bormi?")
    assert wants_human("admin kerak", extra_keywords=["admin"])
    assert detect_script("Salom") == "uz"
    assert detect_script("Қалайсиз") == "uz_cyrl"
    assert detect_script("Здравствуйте") == "ru"
    assert "менеджеру" in handoff_reply_for("Позовите человека")


def test_init_data_validation():
    user = validate_init_data(init_data(42), BOT_TOKEN)
    assert user["id"] == 42
    assert validate_init_data(init_data(42), "other:token") is None
    assert validate_init_data(init_data(42, auth_date=int(time.time()) - 3 * 24 * 3600), BOT_TOKEN) is None
    tampered = init_data(42).replace("Dilnoza", "Hacker")
    assert validate_init_data(tampered, BOT_TOKEN) is None


def test_parse_import_rows_groups_variants():
    rows = [
        ["Kategoriya", "Nomi", "Narx", "Tavsif", "Razmer", "Rang", "Qoldiq", "Rasm"],
        ["Ko'ylaklar", "Qora ko'ylak", "250 000", "Yozgi", "42, 44", "qora", 3, "https://x/1.jpg"],
        ["Ko'ylaklar", "Qora ko'ylak", "270,000", "", "46", "qora", 1, ""],
        ["", "", 100, "", "", "", "", ""],
        ["", "Sumka", "abc", "", "", "", "", ""],
    ]
    products, errors = parse_rows(rows)
    assert len(products) == 1
    dress = products[0]
    assert dress["price"] == 250_000 and dress["images"] == ["https://x/1.jpg"]
    assert [v["attrs"]["size"] for v in dress["variants"]] == ["42", "44", "46"]
    assert dress["variants"][2]["price_override"] == 270_000
    assert len(errors) == 2


def test_parse_import_requires_headers():
    _, errors = parse_rows([["foo", "bar"], ["a", "b"]])
    assert errors


def test_rrf_merge_prefers_items_in_both_rankings():
    assert rrf_merge([1, 2, 3], [3, 4])[0] == 3


def test_system_prompt_is_stable_and_contains_rules():
    shop = Shop(id=1, name="Dilnoza Style")
    settings = ShopSettings(
        shop_id=1, faq_text="FAQ", rules_text="Chegirma yo'q", delivery_zones=ZONES, handoff_rules={}, tone="friendly"
    )
    p1 = build_system_prompt(shop, settings, ["- Qora ko'ylak — 250 000 so'm (id 1)"])
    p2 = build_system_prompt(shop, settings, ["- Qora ko'ylak — 250 000 so'm (id 1)"])
    assert p1 == p2  # prompt caching uchun deterministik
    assert "Dilnoza Style" in p1 and "Chegirma yo'q" in p1 and "handoff_to_human" in p1
    assert "20 000 so'm" in p1
    assert fmt_sum(1250000) == "1 250 000 so'm"
    note = build_state_note("cart", {"items": [], "subtotal": 0}, "Aziza", {"phones": {"[PHONE_1]": "+998"}})
    assert "Aziza" in note and "[PHONE_1]" in note and "+998" not in note


def test_history_alternates_roles_and_masks_phones():
    msgs = [
        Message(id=1, role="staff", content="Assalomu alaykum"),
        Message(id=2, role="customer", content="Salom"),
        Message(id=3, role="customer", content="Raqamim 90 123 45 67"),
        Message(id=4, role="ai", content="Rahmat"),
        Message(id=5, role="customer", content="Qachon?"),
    ]
    masker = PhoneMasker()
    turns = to_llm_messages(msgs, masker, summary="oldin sumka so'ragan")
    roles = [t["role"] for t in turns]
    assert roles[0] == "user" and all(a != b for a, b in zip(roles, roles[1:], strict=False))
    joined = str(turns)
    assert "[PHONE_1]" in joined and "123 45 67" not in joined
    assert "oldin sumka" in turns[0]["content"][0]["text"]
