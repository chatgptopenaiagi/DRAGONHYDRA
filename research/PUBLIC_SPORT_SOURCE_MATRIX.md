# Controlled sports source research — 2026-09-24

One external dataset is enabled. Three initial candidates were reviewed; one replacement was added after StatsBomb license extraction remained unreliable. This is four audited candidates, not four active collectors.

| Source | Access / license / terms | Rate policy | Data classes | Reliability / temporal precision | DRAGONHYDRA use |
|---|---|---|---|---|---|
| [UEFA](https://www.uefa.com/termsconditions/) | Official sports source; web viewing; section 6.2 prohibits automated collection | No data requests permitted | Competition and fixture content, not collected | Primary organization; no data timestamps collected | SOURCE_BLOCKED; REASON=TERMS_BLOCKED; TERMS_BOUNDARY=6.2; ALTERNATIVE_SOURCE=OpenFootball |
| [The Odds API](https://the-odds-api.com/liveapi/guides/v4/) | Documented API; [terms](https://the-odds-api.com/terms-and-conditions.html) reviewed; key required, not enabled | Future adapter: account quota, official 429 handling; local minimum 2 seconds, no bypass | Events, bookmakers, markets, selections, decimal/American prices, update times | Aggregator; commence_time and last_update fields, source delays possible | AUTH_REQUIRED / future adapter; no live odds used |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | Research dataset README; LICENSE.pdf extraction UNRELIABLE; TERMS_STATUS=UNVERIFIED, LICENSE_STATUS=UNVERIFIED | Data ingestion disabled | README independently lists competitions, matches, events, lineups, selected 360 | Provider-published dataset; exact license meaning not inferred from corrupt glyphs | Replaced as demo data source; preserve PDF/extraction evidence only |
| [OpenFootball](https://github.com/openfootball/football.json) | Documented public raw JSON; [CC0-1.0](https://raw.githubusercontent.com/openfootball/football.json/master/LICENSE.md), readable official text | One fixed file, 2-second interval, no automatic retries; robots 404=ABSENT | Competition, round, fixture date/local time, teams, full-time score | Community maintained; not official league authority. README reports daily JSON generation but upstream edits are not guaranteed daily. No verified kickoff timezone or historical availability | ENABLED; historical fixture demo; confidence capped 0.8 |

Demo URL: `https://raw.githubusercontent.com/openfootball/football.json/master/2023-24/en.1.json`.

No rejection was falsely attributed to robots: the active raw host had no robots file. UEFA was rejected by terms before robots/data access. StatsBomb was blocked by UNVERIFIED license/terms. SofaScore and Flashscore were not accessed for data.

Source review notes in `research/browser_research` explicitly label research tool/terminal origin. They are not rendered Desktop observations. No unsupported injury gossip, sensitive traits, live odds or player profiling were collected.
