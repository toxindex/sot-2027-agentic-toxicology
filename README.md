# Agentic toxicology with ToxIndex

Connect your AI agent to ToxIndex, then build things with it. Companion to the
SOT 2027 CE course *Integrated Databases and Tools for Agentic Toxicology*.

## Connect

1. Sign in at **[platform.toxindex.com/connect](https://platform.toxindex.com/connect)**.
2. Click **Create API key** and copy it (it is shown once).
3. Add ToxIndex to your agent:

```bash
# Claude Code
claude mcp add --transport http toxindex https://platform.toxindex.com/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

# Codex
export TOXINDEX_API_KEY=YOUR_API_KEY
codex mcp add toxindex --url https://platform.toxindex.com/mcp --bearer-token-env-var TOXINDEX_API_KEY
```

Cursor and other MCP clients take this entry (VS Code: under `servers` in `.vscode/mcp.json`):

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

The claude.ai and ChatGPT web connectors are not supported yet.

**Check it works:** ask *"Using ToxIndex, is oxybenzone (CAS 131-57-7) a germ cell
mutagen? Show the evidence."* You should get a GHS verdict, the studies and
predictions behind it, and where they conflict.

## What to build

Give one of these to a coding agent in an empty folder. If it is unsure which tool
fits, tell it to start with `toxindex_search`.

- **Hazard profile:** a CLI that takes a chemical name and prints a GHS verdict per
  endpoint, the evidence behind each, and the data gaps.
- **Batch screen:** read `chemicals.csv` and write a table of genotoxicity,
  carcinogenicity and reproductive verdicts, flagging conflicting evidence.
- **Exposure limits side by side:** chart every IRIS, ATSDR, AEGL, OSHA and NIOSH
  limit for a chemical on one scale.
- **Safer alternatives:** rank candidate replacements (as SMILES) against the
  chemical they replace.
- **Cited answers:** answer a regulatory question from ToxIndex documents, quoting
  the passage behind every claim.
- **Ask the data:** find the data bricks about endocrine activity and write SQL
  that pulls every record for bisphenol A.
- **Agent-run systematic review:** set up a Sysrev project, have the agent screen
  and record answers with provenance, then export the results.

## No account?

`uv run demo` in this repository runs a small key-free agent on a laptop with
public data. See [docs/local-demo.md](docs/local-demo.md).

MIT licensed.
