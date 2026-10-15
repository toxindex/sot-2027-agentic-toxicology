"""Tool 1 and tool 2: public data.

`kg.py` pulls a small slice of the BioBricks toxicology knowledge graph and
resolves chemical identity against PubChem. Both are public, anonymous, and
pinned to a content hash so a second run reads the same bytes.

The brick is `biobricks-ai/ice`: the NICEATM Integrated Chemical Environment,
published as Parquet tables. BioBricks stores brick assets as DVC objects
addressed by MD5, so a single table can be fetched over plain HTTPS without the
`biobricks` client, without credentials, and without downloading the brick's
other 25 tables. The `biobricks` package is the supported route for real work
(see docs/local-demo.md); this demo takes the direct-HTTPS route so an attendee needs no
token and no 70 MB pull.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from .provenance import Source, Fact, now

# ---------------------------------------------------------------------------
# Pinned public coordinates. Changing a pin changes the answer, so they live
# here in one place rather than inline at the call sites.
# ---------------------------------------------------------------------------

BRICK_REPO = "https://github.com/biobricks-ai/ice"
BRICK_COMMIT = "e19e98e258349058f2620865e45b410add14df29"
BRICK_DVC_BASE = "https://ins-dvc.s3.amazonaws.com/insdvc/files/md5"
# MD5 of the brick/ directory listing recorded in the brick's dvc.lock.
BRICK_DIR_MD5 = "33c62ab6bc3826f9d6821f1f7a24db14"

# The two tables this demo reads, with the MD5 recorded in the brick, so a
# tampered or rotated object is detected rather than trusted.
TABLES = {
    "Cancer": {"md5": "efc23ab9d8d12812c492382a164647cb", "bytes": 367680},
    "ChemicalQC": {"md5": "41bd5c74d61597aed69ef264e1aabd2c", "bytes": 522865},
}

PUBCHEM_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

CACHE = Path(__file__).resolve().parents[2] / "cache"


def _dvc_url(md5: str) -> str:
    return f"{BRICK_DVC_BASE}/{md5[:2]}/{md5[2:]}"


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with tmp.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1 << 20):
                stream.write(chunk)
    tmp.replace(dest)
    return dest


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def brick_listing() -> list[dict]:
    """The brick's own file listing, fetched from the DVC remote.

    This is what makes the pins above checkable: the listing names every table
    in the brick and its MD5, and it is itself addressed by `BRICK_DIR_MD5`.
    """
    path = _download(_dvc_url(BRICK_DIR_MD5) + ".dir", CACHE / "ice" / "brick.dir.json")
    return json.loads(path.read_text())


def load_table(name: str) -> tuple[pd.DataFrame, Source]:
    """Fetch one ICE table and return it with its provenance record."""
    if name not in TABLES:
        raise ValueError(f"Not a pinned table: {name}. Pinned: {sorted(TABLES)}")
    md5 = TABLES[name]["md5"]
    url = _dvc_url(md5)
    path = _download(url, CACHE / "ice" / f"{name}.parquet")
    actual = _md5(path)
    if actual != md5:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"{name}.parquet MD5 mismatch: expected {md5}, got {actual}")
    frame = pd.read_parquet(path)
    version = sorted({str(v) for v in frame.get("Data.Version", frame.get("Data Version", []))})
    source = Source(
        kind="dataset",
        name=f"BioBricks biobricks-ai/ice :: brick/{name}.parquet",
        version=f"brick commit {BRICK_COMMIT[:12]}" + (f", ICE table {version[0]}" if version else ""),
        url=url,
        digest=actual,
        detail={
            "brick_repo": BRICK_REPO,
            "brick_commit": BRICK_COMMIT,
            "upstream": "NICEATM Integrated Chemical Environment (ICE), https://ice.ntp.niehs.nih.gov/",
            "rows": int(len(frame)),
            "bytes": path.stat().st_size,
            "data_license": "U.S. Government work, public domain",
        },
    )
    return frame, source


# ---------------------------------------------------------------------------
# Tool: chemical identity
# ---------------------------------------------------------------------------

# Offline fallback so the 10-minute path still runs behind a firewall that
# blocks PubChem. Both entries are public structures; the CAS is the key.
KNOWN_STRUCTURES = {
    "131-57-7": ("COC1=CC(=C(C=C1)C(=O)C2=CC=CC=C2)O", 4632, "2-Hydroxy-4-methoxybenzophenone"),
    "80-05-7": ("CC(C)(C1=CC=C(C=C1)O)C2=CC=C(C=C2)O", 6623, "Bisphenol A"),
    "103-90-2": ("CC(=O)NC1=CC=C(C=C1)O", 1983, "Acetaminophen"),
}


def resolve_chemical(cas: str) -> tuple[dict, list[Fact]]:
    """CAS number to structure, via PubChem PUG-REST.

    Returns the record plus the facts that support it. A structure is a fact
    like any other: the model's prediction is only about the molecule we fed
    it, so where that molecule came from belongs in the answer.
    """
    facts: list[Fact] = []
    url = (
        f"{PUBCHEM_REST}/compound/name/{cas}/property/SMILES,MolecularFormula,Title/JSON"
    )
    record = None
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        properties = response.json()["PropertyTable"]["Properties"][0]
        record = {
            "cas": cas,
            "cid": properties["CID"],
            "smiles": properties["SMILES"],
            "formula": properties["MolecularFormula"],
            "name": properties["Title"],
        }
        source = Source(
            kind="api",
            name="PubChem PUG-REST compound property",
            version="PUG-REST (no dataset version; live service)",
            url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{record['cid']}",
            detail={"request": url, "cas_queried": cas},
        )
    except Exception as exc:  # noqa: BLE001 - any network failure falls back
        if cas not in KNOWN_STRUCTURES:
            raise
        smiles, cid, name = KNOWN_STRUCTURES[cas]
        record = {"cas": cas, "cid": cid, "smiles": smiles, "formula": "", "name": name}
        source = Source(
            kind="dataset",
            name="agentic_tox.kg.KNOWN_STRUCTURES (offline fallback)",
            version="in-repo table",
            url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
            detail={"reason": f"PubChem unreachable: {type(exc).__name__}", "cas_queried": cas},
        )
    facts.append(
        Fact(
            statement=f"{cas} is {record['name']} (PubChem CID {record['cid']}), SMILES {record['smiles']}",
            source=source,
            value=record,
        )
    )
    return record, facts


# ---------------------------------------------------------------------------
# Tool: measured genotoxicity and carcinogenicity evidence from ICE
# ---------------------------------------------------------------------------

GENOTOX_ASSAYS = ("In Vitro Genotoxicity", "In Vivo Genotoxicity")
CANCER_ASSAYS = (
    "IARC Carcinogenicity",
    "NTP Carcinogenicity",
    "IRIS Carcinogenicity",
    "Report on Carcinogens",
    "OPP Carcinogenicity",
)


def _records(frame: pd.DataFrame, source: Source, cas: str, assays) -> list[Fact]:
    rows = frame[(frame["CASRN"] == cas) & (frame["Assay"].isin(assays))]
    facts = []
    for _, row in rows.iterrows():
        detail = dict(source.detail)
        detail.update(
            {
                "record_id": row["Record.ID"],
                "assay": row["Assay"],
                "endpoint": row["Endpoint"],
                "species": row.get("Species"),
                "reference": row.get("Reference"),
                "record_url": row.get("URL"),
            }
        )
        where = f" in {row['Species']}" if isinstance(row.get("Species"), str) and row["Species"] not in ("Not applicable", "") else ""
        facts.append(
            Fact(
                statement=f"{row['Assay']} / {row['Endpoint']}{where}: {row['Response']}",
                source=Source(
                    kind=source.kind,
                    name=source.name,
                    version=source.version,
                    url=str(row.get("URL") or source.url),
                    retrieved_at=source.retrieved_at,
                    digest=source.digest,
                    detail=detail,
                ),
                value=str(row["Response"]),
            )
        )
    return facts


def genotoxicity_evidence(cas: str) -> list[Fact]:
    """Measured genotoxicity records for one CAS, from the ICE Cancer table."""
    frame, source = load_table("Cancer")
    return _records(frame, source, cas, GENOTOX_ASSAYS)


def carcinogenicity_evidence(cas: str) -> list[Fact]:
    """Authoritative carcinogenicity classifications for one CAS."""
    frame, source = load_table("Cancer")
    return _records(frame, source, cas, CANCER_ASSAYS)


def tox21_identity(cas: str) -> list[Fact]:
    """Whether the chemical is in the Tox21 10K library, and its QC call."""
    frame, source = load_table("ChemicalQC")
    rows = frame[frame["casrn"] == cas]
    facts = []
    for _, row in rows.iterrows():
        detail = dict(source.detail)
        detail.update({"ncgc_id": row["ncgc_id"], "tox21_id": row["tox21_id"], "dtxsid": row["dtxsid"]})
        facts.append(
            Fact(
                statement=(
                    f"Tox21 library sample {row['tox21_id']} ({row['ncgc_id']}, {row['dtxsid']}): "
                    f"NICEATM QC call {row['NICEATM_qc_summary_call']}"
                ),
                source=Source(
                    kind=source.kind,
                    name=source.name,
                    version=source.version,
                    url=f"https://comptox.epa.gov/dashboard/chemical/details/{row['dtxsid']}",
                    retrieved_at=source.retrieved_at,
                    digest=source.digest,
                    detail=detail,
                ),
                value=str(row["NICEATM_qc_summary_call"]),
            )
        )
    return facts


def cached_bytes() -> int:
    """How much has been downloaded into the cache, for the numbers in docs/local-demo.md."""
    if not CACHE.exists():
        return 0
    return sum(p.stat().st_size for p in CACHE.rglob("*") if p.is_file())
