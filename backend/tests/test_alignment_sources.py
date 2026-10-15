from datetime import date

from sqlalchemy import select

from app.imports.alignment_sources import run
from app.models import Country, Outlet, OutletCategory


def test_alignment_labels_dated_and_idempotent(db):
    c = db.scalar(select(Country))
    for dom in ("libyaalhadath.net", "alwasat.ly"):
        if not db.scalar(select(Outlet).where(Outlet.domain == dom)):
            db.add(Outlet(country_id=c.id, name=dom, domain=dom, languages=["ar"], created_via="seed"))
    db.commit()
    out = run(db)
    assert out["added"] >= 3 and "tanasuh.tv" in out["outlets_not_found"]
    hadath = db.scalar(select(Outlet).where(Outlet.domain == "libyaalhadath.net"))
    rows = db.scalars(select(OutletCategory).where(OutletCategory.outlet_id == hadath.id,
                                                   OutletCategory.dimension == "alignment").order_by(OutletCategory.valid_from)).all()
    assert [(r.valid_from, r.valid_to) for r in rows] == [(date(2018, 3, 1), date(2023, 9, 4)), (date(2023, 9, 4), None)]
    assert all(r.value == "east_lna_aligned" and r.evidence_url.startswith("http") and "As published" in r.note for r in rows)
    again = run(db)
    assert again["added"] == 0 and again["already_there"] == out["added"]
