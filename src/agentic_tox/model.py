"""Tool 3: a public predictive model on CPU.

ToxTransformer is a 59.2M-parameter multitask transformer over SELFIES tokens
that predicts binary molecular properties. Code and weights are MIT licensed
and public:

    https://github.com/toxindex/toxtransformer-research

The weights live in that repository's Git LFS store. Rather than make an
attendee install Git LFS and clone 237 MB of history, this module downloads the
one checkpoint file over HTTPS from the pinned commit and verifies it against
the SHA-256 published in the repository's own artifact manifest. The inference
code itself is installed as a pinned git dependency, so the forward pass is
upstream's, not a reimplementation.

Everything here is CPU only. One prediction takes roughly 0.1 s after a ~1 s
model load.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import requests

from .provenance import Source, Fact

REPO = "https://github.com/toxindex/toxtransformer-research"
COMMIT = "e99a7b9d3568950fecd0b19bb6ea2e2238ee03d5"
MODEL_VERSION = "2.1"
PARAMETERS = 59_218_946

RAW = f"https://raw.githubusercontent.com/toxindex/toxtransformer-research/{COMMIT}"
LFS = f"https://media.githubusercontent.com/media/toxindex/toxtransformer-research/{COMMIT}"

# Paths, sizes and SHA-256 digests as published in the upstream manifest
# artifacts/upstream-checkpoint.json at the pinned commit.
ARTIFACTS = [
    {
        "path": "multitask_encoder.pt",
        "url": f"{LFS}/models/toxtransformer/multitask_encoder.pt",
        "bytes": 236_925_619,
        "sha256": "8cae8b6490635e760a4dc00a66fb2626d8b3b8c1fba97fb7e0daee2935deeb1b",
    },
    {
        "path": "properties.json",
        "url": f"{RAW}/models/toxtransformer/properties.json",
        "bytes": 1_188_100,
        "sha256": "d944611315d1ea924b7a1041b2821322f2c096d4ad548ba1dcdce987fd3e00d3",
    },
    {
        "path": "spvt_tokenizer/selfies_property_val_tokenizer.json",
        "url": f"{RAW}/models/toxtransformer/spvt_tokenizer/selfies_property_val_tokenizer.json",
        "bytes": 155,
        "sha256": "dba5bd91a0d72950d4ae9bbd414e89fe5b5a711548bc62e47168b6436f3948b0",
    },
    {
        "path": "spvt_tokenizer/selfies_tokenizer.json",
        "url": f"{RAW}/models/toxtransformer/spvt_tokenizer/selfies_tokenizer.json",
        "bytes": 85_504,
        "sha256": "232ae9453c5bce87b5bc7e792749b6fb84198e6eaa2397fdad0099a3f9c99211",
    },
]

CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "cache" / "toxtransformer"


@dataclass(frozen=True)
class Endpoint:
    """One of the checkpoint's 6,647 properties, selected for this demo.

    `index` is the model's own output index; `property_id` is the stable
    identifier in the bundled catalog. Both are pinned so a catalog change
    upstream is caught instead of silently shifting which assay is predicted.
    """

    key: str
    index: int
    property_id: str
    title: str
    catalog_source: str


ENDPOINTS = {
    e.key: e
    for e in [
        Endpoint(
            "bacterial_mutagenicity",
            2863,
            "631913ab9f3334ffe372ff85a5d9316c",
            "in vitro bacterial mutagenicity assessment",
            "ice",
        ),
        Endpoint(
            "salmonella_mutagenicity_cpdb",
            3830,
            "df4c42b8626950152a32c7b99e8c3bdc",
            "salmonella mutagenicity assessment from cpdb carcinogenic database",
            "pubchem",
        ),
        Endpoint(
            "ccris_mutagenicity",
            1799,
            "bc227722c5c4d509967d051cee951bb9",
            "genotoxicity screening in ccris: mutagenicity assessment of small molecules",
            "pubchem",
        ),
        Endpoint(
            "atad5_dna_damage",
            1262,
            "b9c7e2a96126e4716024b5a0ad72e2ba",
            "atad5 expression assay for dna damage detection",
            "Tox21",
        ),
        Endpoint(
            "p53_activation",
            1261,
            "b8262b0b3b98d62ae49de1ff95b571fc",
            "detection of p53 activators via chemical assay",
            "Tox21",
        ),
    ]
}

MUTAGENICITY_ENDPOINTS = (
    "bacterial_mutagenicity",
    "salmonella_mutagenicity_cpdb",
    "ccris_mutagenicity",
)
DNA_DAMAGE_ENDPOINTS = ("atad5_dna_damage", "p53_activation")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_weights(progress=print) -> Path:
    """Download and verify the checkpoint bundle. Idempotent."""
    for artifact in ARTIFACTS:
        dest = CHECKPOINT_DIR / artifact["path"]
        if dest.exists() and _sha256(dest) == artifact["sha256"]:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        megabytes = artifact["bytes"] / 1e6
        progress(f"   downloading {artifact['path']} ({megabytes:.1f} MB) from {artifact['url']}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        with requests.get(artifact["url"], stream=True, timeout=600) as response:
            response.raise_for_status()
            with tmp.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1 << 22):
                    stream.write(chunk)
        tmp.replace(dest)
        actual = _sha256(dest)
        if actual != artifact["sha256"]:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"{artifact['path']} SHA-256 mismatch: expected {artifact['sha256']}, got {actual}"
            )
    return CHECKPOINT_DIR


_MODEL = None


def load(progress=print):
    """Load the checkpoint once per process, on CPU."""
    global _MODEL
    if _MODEL is None:
        import torch
        from toxtransformer_research.checkpoint import load_checkpoint

        fetch_weights(progress=progress)
        torch.set_num_threads(1)
        _MODEL = load_checkpoint(str(CHECKPOINT_DIR), device="cpu")
    return _MODEL


def predict(smiles: str, endpoint_key: str, progress=print) -> Fact:
    """Predict one endpoint for one structure, with provenance."""
    from toxtransformer_research.checkpoint import predict_checkpoint

    endpoint = ENDPOINTS[endpoint_key]
    model = load(progress=progress)
    if model.tokenizer.num_assays <= endpoint.index:
        raise RuntimeError("Checkpoint has fewer properties than this demo pins")
    result = predict_checkpoint(model, smiles, endpoint.index)
    probability = result["probability"]
    weights = ARTIFACTS[0]["sha256"]
    source = Source(
        kind="model",
        name=f"ToxTransformer v{MODEL_VERSION} :: property {endpoint.index} ({endpoint.key})",
        version=f"weights sha256 {weights[:12]}, code commit {COMMIT[:12]}, {PARAMETERS:,} params, CPU float32",
        url=REPO,
        digest=weights,
        detail={
            "property_id": endpoint.property_id,
            "property_title": endpoint.title,
            "catalog_source": endpoint.catalog_source,
            "smiles": smiles,
            "probability": probability,
            "code_license": "MIT",
            "weights_license": "MIT",
            "inference": "structure only, no observed context labels",
        },
    )
    return Fact(
        statement=(
            f"ToxTransformer p(active) = {probability:.3f} for '{endpoint.title}'"
            f" [{endpoint.catalog_source}]"
        ),
        source=source,
        value=probability,
    )


def predict_panel(smiles: str, endpoint_keys, progress=print) -> list[Fact]:
    return [predict(smiles, key, progress=progress) for key in endpoint_keys]
