# CORE NEXT private web runtime

This is the web runtime of one isolated DRAGONHYDRA CORE NEXT installation.
Apache serves that profile's Joomla document root; PHP runs the authenticated
server-side bridge; MariaDB owns its Joomla schemas. The Python application owns
sports data and jobs in its separate SQLite database. The reserved MariaDB core
schema is not another sports-data writer.

The locked A9 Apache/PHP/MariaDB/Joomla runtime binaries are reused with their
recorded hashes. `payload-manifest.json` identifies the actual CORE NEXT source,
provisioning hook and newly built component ZIP independently of that third-party
runtime provenance. Archive or build inspection does not establish installation
or clean-machine compatibility.

Use the unified Setup and this instance's uniquely named shortcuts. Its profile
is `C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles\core-next-<GUID>\installation-profile.json`.
The profile binds application and state directories, the owning service, ports,
MariaDB schema/user identities, Joomla session suffix, PHP session name and
WebView storage. It must agree with protected `state/workstation.json` before any
provisioning operation. Original-installation paths and unowned services are
rejected. No application credentials or live configuration belong in this payload.

The owned supervisor performs database bootstrap, Joomla installation/configuration
and child-process lifecycle after validation. Do not run low-level bootstrap or
repair commands independently. It writes only that profile's `site`, `mysql-data`,
`web-config`, `web-logs`, `web-temp` and `web-sessions` state directories. Apache,
MariaDB and Python bind the profile's loopback ports. Private runtime directories
are prepended only to managed child-process PATH; machine PATH is not changed.

Provider schedules start disabled. Optional local AI is independent of browsing.
The Control Center reads authenticated cached registry observations; refresh does
not acquire provider data, generate forecasts, install packages or restart services.
The bridge validates this exact installation identity and never substitutes the
original workstation's backend.

Repair explicitly selects the existing `/PROFILE` and preserves its state and
credentials. Uninstall validates ownership, removes that instance's application,
service and shortcuts, and retains its private state. See the root `INSTALLATION.md`
and the separate release acceptance report for the actual supported scope.
