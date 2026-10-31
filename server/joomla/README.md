# DRAGONHYDRA Joomla administration 0.3.0

Build from the development root:

```powershell
py -3.14 -B scripts/build_joomla.py
py -3.14 -B -m unittest discover -s tests -p test_joomla_package.py -v
```

The resulting `dist/pkg_dragonhydra-0.3.0.zip` contains the administrator component `com_dragonhydra`. Install it through Joomla's extension installer on a **product-owned Joomla 6 instance**. This builder does not alter or install into an existing XAMPP site. PHP cURL is required. PHP 8.5 CLI lint is distinct from testing the required packaged Apache/PHP 8.4 integration.

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
