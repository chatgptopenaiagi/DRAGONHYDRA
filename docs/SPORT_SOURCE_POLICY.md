# Public sports source policy

Only exact operator-reviewed source URLs are eligible. Access permission, licensing and robots are separate gates. ALLOWED_RESEARCH and a supported license are insufficient without explicit VERIFIED terms and license review. UNVERIFIED remains a first-class state and prevents data fetching. Reviews expire after 30 days.

OpenFootball's official [README](https://github.com/openfootball/football.json) documents raw JSON access, and its [plain-text license](https://raw.githubusercontent.com/openfootball/football.json/master/LICENSE.md) is CC0-1.0. Local copies and SHA-256 policy receipts support this demo's bounded use. The raw host returned 404 for robots, recorded as ABSENT. This does not grant rights by itself.

StatsBomb's README independently describes a research dataset, but no reliable complete license extraction was established in this block. Both the earlier custom extraction and pinned pypdf output have invalid glyphs. TERMS_STATUS and LICENSE_STATUS remain UNVERIFIED. No StatsBomb match data was fetched or ingested. Never infer legal terms from the corrupted extraction. Its original PDF, extractor output and status receipts are preserved.

UEFA [terms, section 6.2](https://www.uefa.com/termsconditions/) prohibit automated collection. SOURCE_BLOCKED / TERMS_BLOCKED; no sports data scraping was attempted. Alternative: OpenFootball. Robots was not fetched because the terms gate already refused data collection.

The Odds API [official documentation](https://the-odds-api.com/liveapi/guides/v4/) describes authenticated API access. Its [terms](https://the-odds-api.com/terms-and-conditions.html) support research/dashboard use with restrictions on raw-data redistribution. It is AUTH_REQUIRED / NOT_ENABLED here; no key was requested or used, no account created, no quota consumed. Authentication and plan-specific policy belong to the next source-adapter block.

No SofaScore/Flashscore extraction, paywall bypass, CAPTCHA solving, identity rotation, private API inspection or protected database collection occurred. Four candidates appear in the research audit because OpenFootball replaced the unverified StatsBomb candidate; only one external dataset was fetched. There is no crawler.

Extraction receipts preserve SOURCE_URL, RETRIEVED_AT, CONTENT_HASH, EXTRACTION_METHOD and EXTRACTION_STATUS. Quality checks reject empty text, replacement glyphs, control characters and heavily corrupted English. Passing a heuristic alone never approves terms: explicit scoped review is additionally required. The original source bytes and output hashes remain distinguishable.
