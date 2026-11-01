# DRAGONHYDRA Joomla sports workspace 0.4.1-dev.2

Build from the development root:

```powershell
py -3.14 -B scripts/build_joomla.py
py -3.14 -B -m unittest discover -s tests -p test_joomla_package.py -v
```

The resulting `dist/pkg_dragonhydra-0.4.1-dev.2.zip` contains the existing
`com_dragonhydra` administrator component, its native Site workspace, scoped media,
and the `cassiopeia_dragonhydra` child template. The package installs the child
template first. Install through Joomla's extension installer on a **product-owned
Joomla 6 instance**, after preserving that site's active Home, menu/module/template
records and deployed files. The builder changes no installed site. PHP cURL is
required. CLI lint is distinct from testing the selected Apache/PHP web runtime.

The component postflight calls its `FrontendSetup::apply()` migration. It uses
Joomla's Menu table to create or reuse one DRAGONHYDRA Home for each applicable
language and assign the installed child-template style to those Home items only.
Original menu items and articles remain. Published site modules retain their
published state and assignments on every other page; the migration removes positive
assignments to the managed Home or adds negative exclusions for all-page modules.
Applying again reuses the same Home/style/extension identities and creates no sports
records. The new child overrides only its own index; Joomla core and Cassiopeia
parent files remain unchanged.

The Site view's anonymous output is a branded sign-in shell. Protected workspace
data requires a genuine Joomla Site session and existing component read permission;
an Administrator session is not assumed to be shared. The PHP bridge reads its
protected secret server-side. No pairing token or administrator password belongs in
HTML, JavaScript, links, browser storage or package inputs. Owner credential rotation
therefore does not require source edits or rebuilds. Overview and browsing pages perform retained-data reads. Explicit Analysis navigation
uses existing statistical calculations; it does not submit provider imports or
language-model jobs. Existing export requests are explicit
Joomla POST-token-protected actions. Administration retains its separate permission
and session boundary.

For a manually verified extension installation, the same migration can be reapplied
after bootstrapping that exact Joomla instance and loading
`administrator/components/com_dragonhydra/src/Service/FrontendSetup.php`. Its return
value identifies managed Home/style IDs and assignment changes. Back up first; do
not run it against a different instance because another loopback API responds.

Rollback uses the matching pre-deployment database-consistent backup for Home/menu/
module/template/extension records and the corresponding backed-up component/template
files. No generic uninstall or live storage-directory copy is a verified rollback.
The kernel's sports database remains outside this presentation migration.

Set the component's Options to the recorded kernel loopback endpoint and an absolute path to the protected bridge-secret file. The file contains the same UTF-8 secret as the kernel's bridge configuration (at least 32 bytes). Keep it outside the web root and grant read permission only to the actual product web and kernel service identities. Back it up using the product's protected configuration recovery procedure. Component params store the **file path**, never secret bytes. Installer provisioning and service-account file permissions still require whole-product installation evidence.

Joomla authenticates administrators. `core.manage` allows reading the administration screens; `dragonhydra.import` allows bounded capability tests, imports and cancellation. Mutations verify Joomla POST CSRF tokens. `core.options` protects connection configuration. No browser-supplied administrator flag is accepted. The kernel must enable the trusted bridge only for this product instance and validate signatures, nonce replay and clock skew.

The server signs these newline-separated UTF-8 fields using HMAC-SHA256:

```text
METHOD
/dragon/api/v1/PATH_WITH_QUERY
UNIX_TIMESTAMP
RANDOM_NONCE
joomla:USER_ID
admin_OR_reader
SHA256_EXACT_REQUEST_BODY
```

Headers are `X-Dragon-User`, `X-Dragon-Roles`, `X-Dragon-Time`, `X-Dragon-Nonce`, and `X-Dragon-Signature`. GET signs an empty body; typed POST signs `{}`. Role `admin` is emitted only when the authenticated Joomla user has import permission. The random nonce is 32 hexadecimal characters. No replay is safe merely because a signature is valid: the kernel owns nonce retention/rejection and a bounded clock window. The PHP transport accepts numeric loopback addresses, refuses redirects and userinfo, disables environment proxies, verifies HTTPS certificates, and limits connection/response time and response bytes.

Data sources exposes returned source coverage and import counts. Import public results submits a durable job, opens its progress screen, and provides View imported matches after success. The fixture browser opens the same canonical kernel match IDs as the dashboard. Other sections accurately show existing kernel capabilities and the administration actions not enabled in this version. They do not present placeholder mutation controls.

Joomla owns only extension configuration, permissions and presentation. It creates no second sports database. The no-op 0.3.0 migration records the extension version through Joomla's schema tracker. Uninstall retains the kernel's databases, raw evidence, jobs, model files and vault. Removing credentials or sports data requires a separate explicit product-data operation.

Fixtures exercise the actual PHP HTTP/HMAC transport and package structure; they do not prove extension installation, Joomla ACL execution or a real kernel import. Those are separate integration checks.

Sources: [Joomla component documentation](https://manual.joomla.org/docs/building-extensions/components/), [manifests](https://manual.joomla.org/docs/building-extensions/install-update/installation/manifest/), and [package layout](https://manual.joomla.org/docs/building-extensions/install-update/installation/package/).
