# Integrated databases and tools for agentic toxicology

A small, self-contained demo for the SOT 2027 virtual CE course talk of the same
name. It shows three things working together on a laptop, with no cloud account,
no API key and no licence negotiation:

1. **Public data.** A slice of the BioBricks toxicology knowledge graph, fetched
   by content hash, plus PubChem for chemical identity.
2. **A public model.** ToxTransformer, MIT licensed, 59.2 million parameters,
   running on CPU in about a tenth of a second per prediction.
3. **An agent loop.** A planner that picks the tools, compares measured data
   against prediction, and prints the source, version and timestamp for every
   single fact it states.

The question it answers out of the box is: *is oxybenzone (CAS 131-57-7) likely
mutagenic, and what does the evidence say?*

## The 10-minute path

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and
nothing else. uv installs the pinned Python for you.

```bash
git clone https://github.com/toxindex/sot-2027-agentic-toxicology
cd sot-2027-agentic-toxicology
uv run demo
```

That is the whole demo. It will:

* resolve the CAS number to a structure through PubChem,
* download two Parquet tables from the public BioBricks `ice` brick and verify
  their MD5 against the brick's own record,
* download the ToxTransformer checkpoint once and verify its SHA-256 against the
  manifest published in the model's repository,
* run five model endpoints on CPU,
* print an answer in which every line is traceable.

Ask something else:

```bash
uv run demo "Is bisphenol A (CAS 80-05-7) genotoxic or carcinogenic?"
uv run demo --json > trace.json       # the full machine-readable trace
uv run pytest -q                      # six tests, the no-key path (or: make test)
make notebook                         # execute demo.ipynb end to end
```

`make demo` and `python demo.py` do the same thing as `uv run demo`.

### Measured runtime, CPU only

Measured on ws4, a Linux workstation on a datacentre-class connection, from a
fresh clone each time:

| Run | Wall clock | What dominates |
|-----|-----------|----------------|
| Cold: fresh clone, empty uv cache, empty data cache | **24 s** | downloading 1.3 GB of wheels and the 237 MB checkpoint |
| Warm: environment and caches in place | **4.0 s** | 1.1 s model load, about 0.1 s per prediction |
| `uv run pytest -q`, warm | 9 s | |
| `make notebook` (executes all cells), warm | 15 s | |

Cold time is almost entirely network. Twenty-four seconds is what a very fast
connection buys; on a 50 Mbit/s hotel or conference link the same 1.5 GB takes
about four minutes, and on a slow or throttled link more. That is the whole
reason the talk should run the warm path live and keep the recording in
`RECORDING.md` as the backup.

### How much it downloads

| Item | Size | Where it goes |
|------|------|---------------|
| Python wheels (PyTorch CPU, RDKit, pandas, pyarrow, numpy) | 1.28 GB downloaded into uv's cache; `.venv` is 41 MB of hardlinks into it | uv cache, `.venv/` |
| ToxTransformer checkpoint and tokenizers | 238 MB | `cache/toxtransformer/` |
| BioBricks ICE tables (`Cancer`, `ChemicalQC`) | 0.9 MB | `cache/ice/` |

So about 1.5 GB in total, of which the environment is by far the larger half.
`make clean` removes `cache/`; deleting `.venv` removes the environment; `uv cache
clean` removes the wheel cache, which is the only thing written outside the
repository. The 1.5 GB is dominated by PyTorch: the data slice is under a
megabyte and the model is 238 MB.

## What you are looking at

```
src/agentic_tox/
  provenance.py   Source and Fact. A fact without a source is a bug.
  kg.py           Tool 1 and 2: the BioBricks ICE slice, and PubChem identity.
  model.py        Tool 3: fetch, verify and run the ToxTransformer checkpoint.
  agent.py        The planner, the tool registry, and the rendered answer.
  cli.py          `uv run demo`.
demo.ipynb        The same path as a notebook, cell by cell.
RECORDING.md      How to screen-record the 3 to 5 minute backup video.
```

### The data

[`biobricks-ai/ice`](https://github.com/biobricks-ai/ice) is the public BioBricks
brick for the **NICEATM Integrated Chemical Environment**
(<https://ice.ntp.niehs.nih.gov/>), 27 Parquet tables of curated toxicity data.
U.S. Government work, public domain.

This demo reads two tables, pinned by the MD5 recorded in the brick's `dvc.lock`
at commit `e19e98e2`:

| Table | Rows | Bytes | MD5 | Used for |
|-------|------|-------|-----|----------|
| `brick/Cancer.parquet` | 10,352 | 367,680 | `efc23ab9d8d12812c492382a164647cb` | genotoxicity and carcinogenicity records |
| `brick/ChemicalQC.parquet` | 13,128 | 522,865 | `41bd5c74d61597aed69ef264e1aabd2c` | Tox21 library membership and QC calls |

Objects are fetched from the BioBricks DVC remote, for example
`https://ins-dvc.s3.amazonaws.com/insdvc/files/md5/ef/c23ab9d8d12812c492382a164647cb`.
That route needs no credentials and no client, which is why the demo uses it. For
real work, install the [`biobricks`](https://pypi.org/project/biobricks/) package
and run `biobricks install ice`, which gives you all 27 tables and keeps them
versioned for you.

Chemical identity comes from the PubChem PUG-REST API
(<https://pubchem.ncbi.nlm.nih.gov/rest/pug>). There is a three-entry offline
fallback table in `kg.py` so the demo still runs behind a firewall that blocks
PubChem, and it says so in the provenance line when it uses it.

### The model

[`toxindex/toxtransformer-research`](https://github.com/toxindex/toxtransformer-research),
pinned at commit `e99a7b9d3568950fecd0b19bb6ea2e2238ee03d5`. Code **and weights
are MIT licensed**. The checkpoint is version 2.1: 59,218,946 parameters, 16
causal transformer layers, 6,647 binary property heads, SELFIES input.

* Inference code is installed as a pinned dependency, so the forward pass is
  upstream's, not a reimplementation.
* Weights come straight from that commit's Git LFS object
  (`media.githubusercontent.com/media/...`), so an attendee needs neither Git LFS
  nor a full clone, and are verified against SHA-256
  `8cae8b6490635e760a4dc00a66fb2626d8b3b8c1fba97fb7e0daee2935deeb1b`, which is
  the digest published in that repository's `artifacts/upstream-checkpoint.json`.

Five of the 6,647 property heads are pinned here by index **and** by the
catalog's stable `property_id`, so an upstream catalog change fails a test rather
than silently moving which assay is predicted:

| Key | Index | Catalog source | Title |
|-----|-------|----------------|-------|
| `bacterial_mutagenicity` | 2863 | ice | in vitro bacterial mutagenicity assessment |
| `salmonella_mutagenicity_cpdb` | 3830 | pubchem | salmonella mutagenicity assessment from cpdb carcinogenic database |
| `ccris_mutagenicity` | 1799 | pubchem | genotoxicity screening in ccris: mutagenicity assessment of small molecules |
| `atad5_dna_damage` | 1262 | Tox21 | atad5 expression assay for dna damage detection |
| `p53_activation` | 1261 | Tox21 | detection of p53 activators via chemical assay |

### The agent

The default planner is deterministic and rule based. It finds the CAS number and
the hazard intent in the question, then calls the tools in a fixed order:
identity, library membership, measured data, then the model, because a prediction
only makes sense once you know what the measured record already says.

An LLM planner is available and is **not** the default:

```bash
export ANTHROPIC_API_KEY=...
AGENTIC_TOX_LLM=anthropic uv run demo        # claude-sonnet-5-5 by default
AGENTIC_TOX_LLM=openai   uv run demo         # OPENAI_API_KEY, gpt-4.1 by default
```

It gets the same six tools with the same provenance plumbing, and `uv add
anthropic` or `uv add openai` installs the client. The no-key path is what the
tests cover and what the talk demonstrates, deliberately: most of the value here
is in the tools and the citation discipline, not in who does the planning.

## Expected output

Abridged; the real output prints a provenance line under every fact.

```
[3] measured_genotoxicity(131-57-7)
    why: measured data outranks any prediction
 - In Vivo Genotoxicity / Micronucleus in Mouse: Negative
   provenance: dataset=BioBricks biobricks-ai/ice :: brick/Cancer.parquet  version=brick commit
   e19e98e25834, ICE table V1.0  digest=efc23ab9d8d12812...  retrieved=2026-10-11T14:46:43Z
   https://manticore.niehs.nih.gov/cebssearch/test_article/131-57-7
 - In Vitro Genotoxicity / Bacterial mutagenicity: Weakly Positive; Negative; Negative
   provenance: ...

[4] predict_mutagenicity(COC1=CC(=C(C=C1)C(=O)C2=CC=CC=C2)O)
 - ToxTransformer p(active) = 0.210 for 'in vitro bacterial mutagenicity assessment' [ice]
   provenance: model=ToxTransformer v2.1 :: property 2863  version=weights sha256 8cae8b649063,
   code commit e99a7b9d3568, 59,218,946 params, CPU float32  ...
 - ToxTransformer p(active) = 0.773 for 'salmonella mutagenicity assessment from cpdb ...' [pubchem]
 - ToxTransformer p(active) = 0.112 for 'genotoxicity screening in ccris ...' [pubchem]

------------------------------------------------------------------------------
ANSWER
------------------------------------------------------------------------------
2-Hydroxy-4-methoxybenzophenone (CAS 131-57-7): the public measured record in ICE is
mixed and mostly negative (1 positive / 2 negative study calls), and ToxTransformer
predicts not active (mean p = 0.365). The weight of the public evidence does not
support a mutagenicity call, but it is not clean.

13 facts, 5 tool calls, 2.8s, 239.1 MB cached locally.
```

The three mutagenicity heads disagree with each other (0.210, 0.773, 0.112), and
that is the most useful thing on the screen. They are three different assay
labels from three different public collections, not three opinions about one
endpoint. An agent that averaged them into a single number and stopped there
would be hiding the only part a toxicologist would want to argue with.

## What this shows, and what it does not

**Shows.** Public toxicology data can be addressed by content hash and verified
rather than trusted. A real multitask model runs on a CPU without a GPU, a
licence or a vendor. An agent can be built so that every claim carries its
source, version and the time it was read, which is the difference between a tool
a regulator can check and a chatbot. Measured data and prediction can be put
side by side in the same answer, with the measured record ranked first.

**Does not show.** That ToxTransformer is fit for any regulatory purpose. That
these binary assay-level heads correspond to an OECD 471 Ames call, a weight of
evidence conclusion, or a classification. Anything about metabolism, exposure,
dose or mixtures. Model validity, applicability domain or calibration: no
performance metrics are computed here, and the upstream repository is explicit
that the historical benchmark numbers are not yet reproducible. The ICE slice is
two tables out of 27, and `Cancer.parquet` holds curated study calls, not raw
study data.

Treat the output as a demonstration of plumbing and provenance. It is not a
hazard assessment.

## Troubleshooting

| Symptom | What to do |
|---------|-----------|
| `uv: command not found` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then restart the shell. |
| Hangs at the 237 MB download | It is one file from `media.githubusercontent.com`. Re-run; the download resumes from scratch but completed files are kept and skipped. |
| `SHA-256 mismatch` or `MD5 mismatch` | The partial file is deleted automatically. Re-run. If it repeats, something between you and the source is rewriting bytes, and that is exactly what the check is for. |
| PubChem request fails | The demo falls back to its three-entry local structure table and says so in the provenance line. For other chemicals, pass the structure in by adding it to `KNOWN_STRUCTURES` in `src/agentic_tox/kg.py`. |
| `No CAS number found in the question` | Put the CAS in the question: `uv run demo "Is X (CAS 123-45-6) mutagenic?"`. The planner is rule based on purpose, and does not guess. |
| It picked a GPU build of PyTorch | It should not: `torch` is pinned to the `pytorch-cpu` index in `pyproject.toml`. If uv's cache grows past about 6 GB, delete `.venv` and `uv.lock` and run `uv sync` again. |
| Corporate proxy blocks S3 or GitHub | Everything is plain HTTPS GET. The three hosts needed are `ins-dvc.s3.amazonaws.com`, `raw.githubusercontent.com` and `media.githubusercontent.com`, plus `pubchem.ncbi.nlm.nih.gov` and `pypi.org`. |
| Tests fail on `test_oxybenzone_prediction_reproduces` | CPU float32 should reproduce to within 2e-3. A different number means a different checkpoint; check the digest in the failure. |

## Licence

MIT, see `LICENSE`. The ICE data is U.S. Government work in the public domain.
ToxTransformer code and weights are MIT. Nothing in this repository is
confidential and no client data is used.
