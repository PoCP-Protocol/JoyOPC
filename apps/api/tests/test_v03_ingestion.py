from pathlib import Path

from app.ingestion import MarketSignalFileImporter, SupplierCatalogImporter

ROOT = Path(__file__).resolve().parents[3]


def test_supplier_catalog_imports_chinese_headers():
    rows = SupplierCatalogImporter().parse(ROOT / "sample_data" / "supplier_catalog.csv")
    assert len(rows) == 5
    first = rows[0].normalized
    assert first["product_name"] == "AI Story Bunny"
    assert first["exclusive_rights"] is True
    assert first["supplier_price"] == 16.8
    assert first["market"] == "US"


def test_market_signal_import_normalizes_rows():
    rows = MarketSignalFileImporter().parse(ROOT / "sample_data" / "market_signals.csv")
    assert len(rows) == 5
    assert rows[0]["source"] == "Marketplace Export"
    assert rows[0]["demand_score"] == 91
    assert rows[3]["competition_score"] == 92
