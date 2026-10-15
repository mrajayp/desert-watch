"""Political-alignment labels for Libyan TV channels, as published by two sources
(see docs/research/outlet_alignment_sources.md). Applied to the channel's own website and
Facebook pages where we hold them. Idempotent.

Each label keeps the source's wording in the note, the source link as evidence, and the date
the source describes. A later label for the same outlet closes the earlier one (valid_to), so the
outlet history shows how labels changed. Outlets with no confident match (TV 218, February,
Al-Mustaqbal, Al-Nabaa, Libya Panorama, Al-Ikhbariyya, Libya al-Watan) are left alone, as are
non-alignment findings (e.g. Al-Masar's negative coverage of Dbeibah)."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Outlet, OutletCategory

WR = "https://ijoc.org/index.php/ijoc/article/download/12698/2983"
WR_DATE = date(2018, 3, 1)       # database compiled March 2018
LCFP = "https://lcfp.org.ly/project/political-propaganda-and-the-lack-of-pluralism-in-libyan-media/?lang=en"
LCFP_DATE = date(2023, 9, 4)     # report released 4 September 2023


def wr(text):
    return f"As published in Wollenberg & Richter (2020), Int. J. of Communication 14, Table 1 (data March 2018): {text}"


def lcfp(text):
    return f"As published by the Libyan Center for Freedom of Press with MENA Media Monitor (Sept 2023, 450 hours of broadcast): {text}"


# domains -> labels (oldest first)
LABELS = [
    (["libya24.tv", "facebook.com/libya24tv"], [
        ("east_lna_aligned", "reported", WR, WR_DATE,
         wr("Libya 24, London, affiliated with 'LNA, pro-Qadhafi', supposedly funded by the United Arab Emirates.")),
    ]),
    (["libyaalhadath.net", "facebook.com/LibyaAlhadathLive", "facebook.com/LibyaAlhadathTV"], [
        ("east_lna_aligned", "reported", WR, WR_DATE,
         wr("Al Hadath, Benghazi, affiliated with 'HoR (LNA)', supposedly funded by the LNA and Saudi Arabia.")),
        ("east_lna_aligned", "reported", LCFP, LCFP_DATE,
         lcfp("Libya Al-Hadath favours Khalifa Haftar, who owns and manages it through one of his sons; 25% of coverage, "
              "89% positive. The report calls the bias 'blatant'.")),
    ]),
    (["facebook.com/AlrasmiaTV"], [
        ("tripoli_gnu_aligned", "reported", WR, WR_DATE, wr("Libya al-Rasmiyya, Tripoli, affiliated with the GNA and funded by the GNA.")),
        ("tripoli_gnu_aligned", "reported", LCFP, LCFP_DATE,
         lcfp("public channel Al-Rasmia shows no political pluralism; its role is limited to serving the Presidential Council "
              "and the Government of National Unity.")),
    ]),
    (["facebook.com/alwataniyaly"], [
        ("tripoli_gnu_aligned", "reported", LCFP, LCFP_DATE,
         lcfp("public channel Al-Watanya shows no political pluralism; its role is limited to serving the Presidential Council "
              "and the Government of National Unity.")),
    ]),
    (["libyaalahrar.tv", "facebook.com/LibyaAlAhrarTV"], [
        ("islamist_leaning", "reported", WR, WR_DATE,
         wr("Libya al-Ahrar, Istanbul, affiliated with the Muslim Brotherhood, supposedly funded by Qatar. "
            "(USIP 2015 called it 'most balanced, cautiously anti-Islamist'; LCFP 2023 found Haftar its most-covered figure, "
            "59% negative. Neither assigns an alignment.)")),
    ]),
    (["tanasuh.tv"], [
        ("islamist_leaning", "reported", WR, WR_DATE, wr("Al Tanasuh, Tripoli, 'Islamist', supposedly funded by Qatar.")),
        ("islamist_leaning", "reported", LCFP, LCFP_DATE,
         lcfp("Al-Tanasuh is affiliated with Dar al-Ifta and favours Grand Mufti Sadiq al-Ghariani (89% positive); "
              "Haftar's coverage 76% negative.")),
    ]),
    (["alwasat.ly", "facebook.com/alwasatnewsly"], [
        ("independent", "likely", LCFP, LCFP_DATE,
         lcfp("Al-Wasat showed no blatant bias toward any actor; Dbeibah led with 20% of coverage, with trends more neutral "
              "or negative than positive. ('Independent' is our reading of that finding.)")),
    ]),
]


def run(s: Session) -> dict:
    added = skipped = closed = 0
    missing = []
    for domains, labels in LABELS:
        for dom in domains:
            o = s.scalar(select(Outlet).where(Outlet.domain == dom))
            if not o:
                missing.append(dom)
                continue
            for value, confidence, url, valid_from, note in labels:
                exists = s.scalar(select(OutletCategory.id).where(
                    OutletCategory.outlet_id == o.id, OutletCategory.dimension == "alignment",
                    OutletCategory.evidence_url == url, OutletCategory.valid_from == valid_from))
                if exists:
                    skipped += 1
                    continue
                # close any open alignment label that started earlier
                for prev in s.scalars(select(OutletCategory).where(
                        OutletCategory.outlet_id == o.id, OutletCategory.dimension == "alignment",
                        OutletCategory.valid_to.is_(None), OutletCategory.valid_from < valid_from)):
                    prev.valid_to = valid_from
                    closed += 1
                s.add(OutletCategory(outlet_id=o.id, dimension="alignment", value=value, confidence=confidence,
                                     evidence_url=url, note=note, status="active", valid_from=valid_from))
                s.flush()
                added += 1
    s.commit()
    return {"added": added, "already_there": skipped, "closed_older": closed, "outlets_not_found": missing}
