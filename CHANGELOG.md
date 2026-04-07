# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0.0] - 2026-04-08

### Added
- **Question type classification**: each discussion post is now tagged as `leetcode`
  (has a direct /problems/ link), `discuss_link` (links to another discussion thread),
  or `discussion` (pure text — interview questions described without a LeetCode number).
  This makes discussion-only interview questions visible for the first time.
- **`question_description` field**: plain-text content extracted via BeautifulSoup,
  stored in full internally and truncated to 2000 chars only at CSV export time.
- **`--since` flag**: filter results to posts from the last N days or weeks
  (e.g. `--since 7d`, `--since 2w`). Validated at the CLI level with a clear error
  message on bad format.
- **Deduplication with `frequency`**: posts sharing the same LeetCode problem slug are
  collapsed into one canonical row. The `frequency` field records how many times that
  problem appeared across all crawled pages.
- **Retry logic with exponential backoff**: HTTP 429 and 5xx responses are retried up to
  3 times (4 total attempts) with 2s/4s/8s backoff via tenacity. JSONDecodeError and
  4xx (non-429) responses fail immediately without retrying.
- **29-test unit suite** covering HTTP resilience, pagination, dedup, time filtering,
  question type classification, HTML stripping, CLI wiring, and CSV truncation.

### Changed
- `run()` no longer saves files internally — callers (`cli.py` or `__main__`) are
  responsible for saving, eliminating a double-write bug.
- `save_by_month()` now accepts `company_tag` parameter — filenames are now
  `leetcode_{company}_interviews_{month}.csv` (was always hardcoded to `google`).
- `--category` is now properly wired through `cli.py` → `run()` → the LeetCode API.
- Page fetch errors now `continue` to the next page instead of `break`-ing the entire
  crawl — a transient 503 on page 3 no longer silently drops pages 4-10.
- `os.makedirs` in `save_by_month` uses `exist_ok=True` to eliminate a TOCTOU race.
- Problem-link detection now requires `leetcode.com` hostname or `/problems/` prefix,
  preventing external URLs from poisoning the dedup key.

### Fixed
- `import json` was only available inside the `if __name__ == '__main__'` block of
  `google_sheets_exporter.py`, causing `NameError` on import.
- `soup.find_all("a")` was called twice per post; now cached in a variable.
- `group_by_month` now casts `created_at` to `str` before calling `.replace()`,
  consistent with `filter_by_since`.
- `company_tag` is sanitized before use in output filenames to prevent path traversal.
- `extract_post_details` now catches `AttributeError`/`TypeError`/`KeyError` so
  unexpected API response shapes (e.g. JSON list instead of dict) return `None`
  instead of crashing the crawl.
