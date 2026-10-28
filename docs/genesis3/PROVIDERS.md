# Provider evidence and connection boundaries

The machine-readable [provider manifest](../../android/dragonhydra_mobile/assets/provider-manifest.json) distinguishes reviewed documentation, implemented adapter, configured authentication, successful request and durable import. These are independent facts. A provider card or official website link is not a connection. Account tiers, fees, quotas, permitted use and geographic availability remain provider-specific.

## Documented authentication

| Provider | Official documentation and access |
| --- | --- |
| The Odds API | [v4 guide](https://the-odds-api.com/liveapi/guides/v4/): `apiKey` query parameter; paid plans may be required for history. |
| Sportmonks | [Authentication](https://docs.sportmonks.com/v3/welcome/authentication): API token in `Authorization` header or `api_token` parameter; provider recommends a protected backend. |
| Sportradar | [Security changes](https://developer.sportradar.com/getting-started/docs/api-security-enhancements): HTTPS and header-based API keys, with changes announced for November 13, 2026. |
| API-FOOTBALL | [API v3](https://www.api-football.com/documentation_v3): `x-apisports-key` header. |
| football-data.org | [v4 examples](https://docs.football-data.org/general/v4/coding_client.html): `X-Auth-Token` header. This is a different source from Football-Data.co.uk. |
| SportsDataIO | [Global API](https://sportsdata.io/developers/api-documentation/global): `Ocp-Apim-Subscription-Key`; [trial data may be scrambled](https://sportsdata.io/help/faq). |
| Betfair | [Getting started](https://support.developer.betfair.com/hc/en-us/articles/115003864651-How-do-I-get-started): account, app key and authorized session token. Website sign-in is not API authorization. |
| Pinnacle | [API access](https://www.pinnacle.com/en/api): application and account-specific approval; endpoint and authentication have not been verified. |
| ADMIRAL | [Official website](https://www.admiral.at/): no official, user-accessible developer API was verified. API NOT VERIFIED. |
| TheOddsAPI | [Documentation](https://theoddsapi.com/docs/): `x-api-key` header; this is a separate provider from the-odds-api.com. |

## Public data

[StatsBomb Open Data](https://github.com/statsbomb/open-data) publishes selected competition, match and event files and has attribution requirements. [OpenFootball](https://github.com/openfootball/football.json) publishes fixtures and results without an API key. [Football-Data.co.uk](https://www.football-data.co.uk/downloadm.php) provides historical CSV data; source terms and the limits of recorded odds times apply. [nflverse](https://github.com/nflverse/nflverse-data), [MoneyPuck](https://www.moneypuck.com/data.htm) and [Cricsheet](https://cricsheet.org/downloads/) provide additional public datasets subject to their own terms. MoneyPuck explicitly asks for attribution and limits unapproved scraping.

`lib/public_sources.dart` implements one explicitly requested, bounded HTTPS
fetch and top-level JSON shape validation for each of OpenFootball's 2025/26
English league file and StatsBomb's open competition list. On 2026-10-28 the
same Dart code fetched 380 and 80 records respectively from Windows; response
bytes, SHA-256 hashes and UTC receipt metadata were preserved in
`release/genesis3/provider-evidence/`. This establishes neither an Android
device test nor an operational database import. The app fetch is in-memory;
its persistence and earliest-usable timestamps remain unknown. Public-source
connectivity on the user's phone is a separate state from this development
verification.

Historical files observed now must retain their actual receipt time. A source match date or source-reported update time is not evidence that DRAGONHYDRA had the file then. Data from different providers must not be combined without verified fixture, market and settlement mappings.

## Authentication limitations

`football_data_org`, `api_football` and `the_odds_api` have read-only connection-test adapters;
their authentication responses have only been mock-tested and no genuine
authenticated request or imported data is established. An unauthenticated
development probe of football-data.org returned HTTP 200 with
`X-Authenticated-Client: anonymous`, so HTTP success by itself must never be
reported as an authenticated connection.

The Odds API requires its key in a query parameter. The app uses HTTPS and does
not log it, but URLs can still be retained by provider or intermediary logs.
The `/v4/sports` catalog is documented as not consuming usage credits; the
adapter makes no odds requests and does not import market records.

An integration that requires credentials is configurable only if a secure credential entry and storage path is actually implemented; consult the mobile build report rather than assuming it exists. The registry does not contain secrets. Google login and OpenAI Platform access require their own supported authorization flows; neither can be inferred from an existing Codex CLI session.
