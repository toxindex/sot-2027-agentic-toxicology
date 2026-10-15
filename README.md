# Agentic toxicology with ToxIndex

Connect your AI agent to ToxIndex and it can assess hazards, pull exposure
limits, query toxicology datasets, run prediction models, search regulatory
documents and run systematic reviews, with the evidence and sources behind every
result. This is the companion repository for the SOT 2027 CE course *Integrated
Databases and Tools for Agentic Toxicology*.

## Connect

1. Go to **[platform.toxindex.com/connect](https://platform.toxindex.com/connect)**
   and sign in or create an account.
2. Click **Create API key**. The key is shown once, so copy it.
3. Add ToxIndex to your agent:

**Claude Code**

```bash
claude mcp add --transport http toxindex https://platform.toxindex.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"
```

**Codex**

```bash
export TOXINDEX_API_KEY=YOUR_API_KEY
codex mcp add toxindex --url https://platform.toxindex.com/mcp --bearer-token-env-var TOXINDEX_API_KEY
```

**Cursor and other MCP clients**: add this server (in VS Code, put the same
entry under `servers` in `.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "toxindex": {
      "type": "http",
      "url": "https://platform.toxindex.com/mcp",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}
```

The claude.ai and ChatGPT web connectors cannot connect yet: they need an OAuth
sign-in, and ToxIndex currently takes an API key.

**Check it works.** Ask your agent:

> Using ToxIndex, is oxybenzone (CAS 131-57-7) a germ cell mutagen? Show the
> evidence behind the verdict.

It should come back with a GHS verdict, the studies and predictions behind it,
where they conflict, and what data is missing.

## What to build

Each of these is a prompt to give a coding agent in an empty folder. If you are
not sure which tool or dataset fits, tell it to start with `toxindex_search`.

- **Hazard profile.** "Build a command-line tool that takes a chemical name and
  prints a one-page hazard profile from the ToxIndex `tox_*` tools: the GHS
  verdict for each endpoint, the evidence behind it, and the data gaps."
- **Batch screen.** "Read `chemicals.csv` (names or CAS numbers) and write a
  table of genotoxicity, carcinogenicity and reproductive toxicity verdicts.
  Flag every chemical whose evidence conflicts."
- **Exposure limits side by side.** "For one chemical, collect every exposure
  limit ToxIndex has (IRIS, ATSDR, AEGL, OSHA, NIOSH) and chart them on one
  scale with the basis of each."
- **Safer alternatives.** "Given a chemical and a list of candidate replacements
  as SMILES, run the ToxIndex hazard and prediction tools on each and rank the
  candidates against the original."
- **Cited answers from regulatory documents.** "Answer a regulatory question by
  searching ToxIndex documents, reading the relevant ones, and quoting the
  passage behind every claim."
- **Ask the data directly.** "List the ToxIndex data bricks, find the ones about
  endocrine activity, and write SQL that pulls every record for bisphenol A."
- **Agent-run systematic review.** "Create a ToxIndex Sysrev project on
  oxybenzone and endocrine disruption, have the agent screen the documents and
  record its answers with provenance, then export the results."

## No account? Run it locally

The repository also has a small demo that needs no account or key. It answers
"is oxybenzone mutagenic?" on a laptop from public data (a BioBricks slice and the
MIT-licensed ToxTransformer model) and prints the source of every fact. You need
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/toxindex/sot-2027-agentic-toxicology
cd sot-2027-agentic-toxicology
uv run demo
```

Details, runtimes and troubleshooting: [docs/local-demo.md](docs/local-demo.md).

## Licence

MIT. The ICE data is U.S. Government work in the public domain; ToxTransformer
code and weights are MIT.
