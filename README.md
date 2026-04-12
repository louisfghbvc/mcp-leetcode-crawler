# LeetCode Discussion Crawler + MCP Server

Crawl LeetCode interview discussion forums, extract structured intelligence with Claude AI,
and expose the data as an MCP (Model Context Protocol) server for Claude Desktop and Claude Code.

## What it does

- Crawls LeetCode discussion forums filtered by company tag (google, meta, amazon, etc.)
- Classifies posts by type (`leetcode`, `discuss_link`, `discussion`)
- Groups and deduplicates discussions by post title + company across pages
- Optionally enriches posts with AI-extracted fields: `problem_name`, `leetcode_url`,
  `interview_stage`, `difficulty`, `reported_outcome`
- Saves to CSV (per-company cache or monthly output)
- Exposes 4 tools over stdio MCP transport for use with Claude Desktop / Claude Code

## Installation

```bash
git clone https://github.com/louisfghbvc/mcp-leetcode-crawler.git
cd mcp-leetcode-crawler
pip install -r requirements.txt
```

## Usage

### CLI

```bash
# Crawl 10 pages of Google interview discussions
python cli.py --company google --pages 10

# Filter to posts from the last 30 days
python cli.py --company google --pages 10 --since 30d

# Crawl and enrich with AI extraction (requires ANTHROPIC_API_KEY)
python cli.py --company google --pages 10 --enrich

# Other companies
python cli.py --company meta --pages 5 --since 7d
```

Available CLI options:
- `--company`: Company tag (default: google)
- `--pages`: Pages to crawl, 15 posts/page (default: 10)
- `--output`: Output CSV path (default: leetcode_interview_questions.csv)
- `--output-dir`: Directory for monthly CSVs (default: output)
- `--since`: Time window filter — `Nd` (days) or `Nw` (weeks), e.g. `--since 14d`
- `--enrich`: AI-extract structured fields from each post (requires `ANTHROPIC_API_KEY`)
- `--verbose`: Debug logging
- `--category`: Discussion category (default: interview-question)

### MCP Server

Register with Claude Desktop or Claude Code:

```bash
# Run directly
python mcp_server.py

# Or register with Claude Desktop
mcp install mcp_server.py
```

The server exposes 4 tools:

| Tool | Description |
|------|-------------|
| `search_discussions(company, days)` | Filter cached posts by company and time window |
| `get_hot_problems(company, limit)` | Top LeetCode problems ranked by discussion frequency |
| `get_thread(post_id)` | Real-time single-thread fetch (no cache) |
| `refresh(company, num_pages, days, enrich)` | Crawl and rebuild on-disk cache |

Cache lives in `./cache/{company}_questions.csv`. Run `refresh` once to populate before
using `search_discussions` or `get_hot_problems`.

### AI Enrichment

When `--enrich` (CLI) or `enrich=True` (MCP `refresh`) is used, each post gets 5 new fields:

| Field | Values |
|-------|--------|
| `problem_name` | LeetCode problem name, or `null` |
| `leetcode_url` | Full problem URL, or `null` |
| `interview_stage` | `phone screen` / `online assessment` / `onsite` / `final round` / `null` |
| `difficulty` | `easy` / `medium` / `hard` / `null` |
| `reported_outcome` | `passed` / `failed` / `no mention` / `null` (null = extraction failed, will retry) |

Cost: ~$0.001/post with `claude-haiku-4-5-20251001`. Already-enriched posts are skipped on re-run.

## Project Structure

```
mcp-leetcode-crawler/
├── crawler.py          # Core crawler: fetch, deduplicate, filter, classify posts
├── extractor.py        # AI extraction layer: Claude Haiku → structured fields
├── mcp_server.py       # MCP server: 4 tools over stdio transport
├── cli.py              # Command-line interface
├── requirements.txt    # Python dependencies
├── test_crawler.py     # Crawler unit tests
├── test_mcp_server.py  # MCP server unit tests (22 tests)
├── test_extractor.py   # Extractor unit tests (12 tests)
├── test_cli.py         # CLI integration tests (2 tests)
└── cache/              # Per-company CSV cache (git-ignored)
```

## Requirements

- Python 3.12+
- `ANTHROPIC_API_KEY` env var (only for `--enrich`)

## License

MIT
