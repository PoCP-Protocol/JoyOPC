from app.content_factory import content_factory
from app.fulfillment_sourcing import score_supplier_nodes
from app.listing_limits import AMAZON_LIMITS, enforce_amazon_copy, validate_amazon_copy
from app.opensource_stack import catalog
from app.sku_matcher import match_master_sku


def test_amazon_limits_enforced():
    copy = enforce_amazon_copy(
        {
            "title": "T" * 300,
            "bullets": ["only one"],
            "description": "D" * 3000,
            "search_terms": "kw " * 200,
        }
    )
    assert len(copy["title"]) <= AMAZON_LIMITS["title"]
    assert len(copy["bullets"]) == 5
    assert validate_amazon_copy(copy) == []


def test_sku_matcher_exact_and_ambiguous():
    catalog_rows = [("JOY-AI-001", "AI Story Teddy"), ("JOY-AI-002", "AI Pocket Translator Toy")]
    exact = match_master_sku("joy-ai-001", catalog_rows)
    assert exact["method"] == "EXACT"
    assert exact["sku"] == "JOY-AI-001"
    unmatched = match_master_sku("UNKNOWN-SKU", catalog_rows)
    assert unmatched["method"] == "UNMATCHED"


def test_cost_optimal_ranks_cheaper_supplier():
    ranked = score_supplier_nodes(
        strategy="COST_OPTIMAL",
        nodes=[
            {"supplier_sku": "EXP", "supplier_price": 40, "lead_time_days": 3, "exclusive_rights": True, "moq": 1},
            {"supplier_sku": "CHEAP", "supplier_price": 8, "lead_time_days": 20, "exclusive_rights": False, "moq": 50},
        ],
    )
    assert ranked[0]["supplier_sku"] == "CHEAP"


def test_opensource_catalog_lists_new_ports():
    data = catalog()
    ids = {row["id"] for row in data["packages"]}
    assert "kuberiva-oms" in ids
    assert "marketeer" in ids
    assert "trademind-ai" in ids
    assert data["amazon_sdk"]["package"] == "python-amazon-sp-api"


def test_content_factory_amazon_is_compliant():
    result = content_factory.generate({"sku": "JOY-AI-001", "name": "AI Story Teddy", "features": ["on-device stories"]})
    assert validate_amazon_copy(result["listings"]["amazon"]) == []
    assert "open-listing-studio" in str(result["inspired_by"])
