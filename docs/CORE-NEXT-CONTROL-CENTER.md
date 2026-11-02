# CORE NEXT System Control Center

The isolated Joomla administrator component defaults to the System Control Center
at `administrator/index.php?option=com_dragonhydra`. It retains the sports Site
workspace, separate Joomla authentication, existing server-side HMAC transport,
Data sources actions, match browsing and durable-job progress/cancellation.

The dev.2 component, package and child template identify as `0.5.0-dev.2`. The header
shows the expected CORE NEXT edition, verified installation/environment identity,
kernel version, build ID and source revision. The public sports header and page
title also identify CORE NEXT. Installation, runtime and browser acceptance are
separate from PHP fixture/package verification.

## Authoritative reads

`ControlCenterModel` first reads authenticated `/dragon/api/v1/modules?scope=all` with schema
`core-next.modules/1`. It requires product `DRAGONHYDRA CORE NEXT` and an exact match
to the trusted component parameter `core_next_installation_id`. Missing binding,
an original-edition backend, a foreign installation, an invalid registry or a
failed transport produces a bounded unavailable message. There is no default
original API endpoint and no fallback status database.

The registry exposes six engines and twelve supporting responsibilities. The
overview totals and layer/category filters derive from those returned IDs, not
fixed counts in the template. All modules and detail pages include the same
build-bound inventory; see [the ownership map](architecture/MODULE-MAP.md).

Display refresh is a passive read. The separate local-observation POST requires
administrator permission, a Joomla form token and a matching installation. It
performs bounded local checks only. Forecast/evaluation forms submit explicit
typed jobs; repeated submissions reuse their idempotency key. Match history shows
stable run/record IDs, input cutoffs, model/ensemble identity and pending outcomes.
No state-changing action is a GET link. The service observer runs without Joomla
being open; evidence age/expiry never changes simply because a page is refreshed.

The Overview and Infrastructure pages additionally read `/system`, retaining its
existing public status/storage fields and checking the same installation identity.
Module detail uses `/modules/{registered-id}`; browser input cannot select an
arbitrary API path. The module-detail response must agree on installation and
module identity. Old administrator URLs map to the new sections: `system` to
Overview, `databases` to Infrastructure, `models` to AI and `research` to Memory.

The interface renders definitions and cached observations for Data, Odds,
Prediction, AI, Memory and Evaluation. It presents versions, descriptions,
dependencies, capabilities, scalar metrics, observation/expiry times, scope and
operation reasons. It does not recompute forecasts or evaluations while browsing.
Unknown state values display UNKNOWN. READY requires parseable bounded observation
timestamps; expired observations display EXPIRED. Missing observations are never
converted to invented measurements. A retained zero is displayed as zero.

Infrastructure installation/restart/restore/cutover operations remain disabled with
reasons. Module mutation advertisements do not become generic buttons or proxy
targets. Data sources links to the existing explicit operations instead. Existing
import/probe/cancel actions retain Joomla POST CSRF and ACL checks and additionally
verify the CORE NEXT installation identity before forwarding a mutation.

## Provisioning and security boundaries

The isolated profile provisions `api_base`, `dashboard_url`, the protected
`bridge_secret_path` and `core_next_installation_id` into component parameters.
Secret bytes remain outside the web root and never enter the model/template,
browser storage, links or JavaScript. Joomla Site and Administrator authentication
remain distinct. The installed management hook supplies candidate-specific database,
cookie and session identities; it is owned by the isolated-profile implementation.

Only HTML-escaped presentation fields are rendered. Backend error contents and
unrecognized identity fields are omitted. The administrator stylesheet is scoped
under `.dhcn-control-center`; the existing sports workspace styles are retained.
The skip link, main landmark, real headings, table captions, visible state labels
and keyboard focus indicators are part of the native administrator screen.

## Verification

Run the existing selected interpreter with `-B` and the verified PHP executable:

```powershell
$env:DRAGONHYDRA_TEST_PHP = 'C:\xampp\php\php.exe'
python -B -m unittest discover -s tests -p test_core_next_joomla_control.py -v
python -B -m unittest discover -s tests -p 'test_joomla*.py' -v
```

The focused suite executes the actual PHP model and templates against counted
synthetic read callbacks. It tests authorization/installation denial before access,
cross-instance rejection, read-only paths, arbitrary-path rejection, unknown and
expired states, preserved zero metrics, escaping, disabled operation reasons and
package identity. Existing fixtures cover HMAC transport, binary export, CSRF/ACL
contracts, preserved Site rendering, migration semantics, package reproducibility
and PHP syntax. `DRAGONHYDRA_TEST_PHP_INI` may select the matching PHP INI explicitly;
these overrides do not change product runtime selection.

The focused suite also passes the real candidate API's complete cached registry
through the actual PHP adapter for Overview, Infrastructure, Modules and every
registered module. It uses the explicit sanitized private snapshot, checks
unchanged observations and zero created jobs, and verifies state, capability and
scalar-metric preservation. Supply the snapshot path through
`DRAGONHYDRA_CHARACTERIZATION_SNAPSHOT`; no private snapshot is bundled with tests.

Live acceptance must separately show an actual Joomla administrator session, bound
registry values, distinct candidate cookies and the retained sports homepage. GET
read invariants must also be checked against the kernel's own status/job/provider
evidence. Fixture success alone is not an installation or live integration claim.
