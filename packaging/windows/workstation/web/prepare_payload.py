"""Assemble a private Windows web runtime from pinned, verified local inputs.

Never reads an installed site's configuration, data or logs. No service starts.
The generated manifest is an inventory, not a claim of a clean-machine test.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path, PurePosixPath


JOOMLA_SHA256 = "eaafc68b5990d7b9dd9156656d4c3c3547743d1d7a85682a92e2f9121b58f018"
PHP_SHA256 = "53db2047139bdfb8e6c7c7d5860a0a6a2a4f1dcac49fcf18ae610a14d8ccdf5b"
APACHE_FILES = (
    "bin/httpd.exe", "bin/libhttpd.dll", "bin/libapr-1.dll", "bin/libaprutil-1.dll",
    "bin/libapriconv-1.dll", "bin/pcre.dll", "bin/pcre2-8.dll", "bin/zlib1.dll",
    "modules/mod_authz_core.so", "modules/mod_authz_host.so", "modules/mod_dir.so",
    "modules/mod_mime.so", "modules/mod_log_config.so", "modules/mod_headers.so",
    "modules/mod_alias.so", "modules/mod_rewrite.so", "modules/mod_proxy.so",
    "modules/mod_proxy_http.so", "conf/mime.types", "ABOUT_APACHE.txt", "CHANGES.txt",
    "INSTALL.txt", "LICENSE.txt", "NOTICE.txt", "README.txt",
)
CRT_FILES = (
    "concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "vcruntime140.dll",
    "vcruntime140_1.dll",
)
MARIADB_FILES = (
    "bin/mariadbd.exe", "bin/mysqld.exe", "bin/mysql_install_db.exe",
    "bin/mariadb-install-db.exe", "bin/mariadb.exe", "bin/mysql.exe",
    "bin/mariadb-admin.exe", "bin/mysqladmin.exe", "bin/mariadb-dump.exe",
    "bin/mysqldump.exe", "bin/server.dll", "COPYING", "CREDITS", "README.md", "THIRDPARTY",
    "share/errmsg-utf8.txt", "share/english/errmsg.sys", "share/fill_help_tables.sql",
    "share/maria_add_gis_sp.sql", "share/maria_add_gis_sp_bootstrap.sql",
    "share/mysql_performance_tables.sql", "share/mysql_sys_schema.sql",
    "share/mysql_system_tables.sql", "share/mysql_system_tables_data.sql",
    "share/mysql_test_data_timezone.sql",
) + tuple("bin/" + name for name in CRT_FILES)
PHP_FILES = (
    "php.exe", "php8ts.dll", "php8apache2_4.dll", "brotlicommon.dll", "brotlidec.dll",
    "icudt77.dll", "icuin77.dll", "icuio77.dll", "icuuc77.dll", "libcrypto-3-x64.dll",
    "libssl-3-x64.dll", "libsasl.dll", "libsodium.dll", "libssh2.dll", "nghttp2.dll",
    "ext/php_curl.dll", "ext/php_fileinfo.dll", "ext/php_gd.dll", "ext/php_intl.dll",
    "ext/php_mbstring.dll", "ext/php_mysqli.dll", "ext/php_openssl.dll",
    "ext/php_pdo_mysql.dll", "ext/php_sodium.dll", "ext/php_zip.dll",
    "license.txt", "readme-redist-bins.txt", "README.md", "news.txt", "snapshot.txt",
)
JOOMLA_ROOTS = frozenset((
    "administrator", "api", "cache", "cli", "components", "files", "images", "includes",
    "installation", "language", "layouts", "libraries", "media", "modules", "plugins",
    "templates", "tmp", "htaccess.txt", "index.php", "LICENSE.txt", "README.txt",
    "robots.txt.dist", "web.config.txt",
))
SYSTEM_IMPORTS = frozenset((
    "kernel32.dll", "ntdll.dll", "user32.dll", "advapi32.dll", "ws2_32.dll", "mswsock.dll",
    "rpcrt4.dll", "shell32.dll", "ole32.dll", "oleaut32.dll", "crypt32.dll", "secur32.dll",
    "bcrypt.dll", "bcryptprimitives.dll", "normaliz.dll", "shlwapi.dll", "version.dll",
    "iphlpapi.dll", "dnsapi.dll", "wldap32.dll", "winmm.dll", "gdi32.dll", "comdlg32.dll",
    "psapi.dll", "dbghelp.dll", "netapi32.dll", "winhttp.dll", "wininet.dll", "msvcrt.dll",
    "ucrtbase.dll", "userenv.dll", "powrprof.dll", "dwmapi.dll", "winspool.drv",
    "authz.dll", "ncrypt.dll", "cryptbase.dll", "wintrust.dll", "wtsapi32.dll", "propsys.dll",
    "comctl32.dll", "imagehlp.dll", "setupapi.dll", "hid.dll", "mpr.dll", "sensapi.dll",
))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pe_imports(path: Path) -> tuple[int, list[str]]:
    """Read PE machine/import tables without loading untrusted DLLs."""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not a PE image: {path.name}")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE signature: {path.name}")
    machine, sections = struct.unpack_from("<HH", data, pe + 4)
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20B else 96)
    import_rva = struct.unpack_from("<I", data, directories + 8)[0]
    headers = optional + optional_size

    def offset(rva: int) -> int:
        for index in range(sections):
            section = headers + index * 40
            size, address, raw_size, raw = struct.unpack_from("<IIII", data, section + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError(f"Unmapped PE RVA: {path.name}")

    imports: list[str] = []
    if import_rva:
        descriptor = offset(import_rva)
        while any(data[descriptor:descriptor + 20]):
            name_rva = struct.unpack_from("<I", data, descriptor + 12)[0]
            begin = offset(name_rva)
            end = data.index(b"\0", begin)
            imports.append(data[begin:end].decode("ascii").lower())
            descriptor += 20
    return machine, imports


def windows_file_version(path: Path) -> tuple[int, int, int, int]:
    """Read the selected binary's version resource; never execute it."""
    library = ctypes.WinDLL("version", use_last_error=True)
    library.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    library.GetFileVersionInfoSizeW.restype = ctypes.c_ulong
    library.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    library.GetFileVersionInfoW.restype = ctypes.c_int
    library.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    library.VerQueryValueW.restype = ctypes.c_int
    handle = ctypes.c_ulong()
    size = library.GetFileVersionInfoSizeW(str(path), ctypes.byref(handle))
    if not size:
        raise ValueError(f"Runtime version resource missing: {path.name}")
    buffer = ctypes.create_string_buffer(size)
    if not library.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ValueError(f"Runtime version resource unreadable: {path.name}")
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not library.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        raise ValueError(f"Runtime fixed version missing: {path.name}")
    fixed = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
    return fixed[2] >> 16, fixed[2] & 0xffff, fixed[3] >> 16, fixed[3] & 0xffff


def copy_files(source: Path, target: Path, names: tuple[str, ...]) -> None:
    for name in names:
        src = source / name
        if not src.is_file():
            raise FileNotFoundError(f"Allowlisted runtime input missing: {src}")
        dst = target / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def verified_zip(path: Path, expected: str) -> zipfile.ZipFile:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"Pinned archive checksum mismatch: {path.name}")
    archive = zipfile.ZipFile(path)
    for entry in archive.infolist():
        pure = PurePosixPath(entry.filename)
        if pure.is_absolute() or ".." in pure.parts or "\\" in entry.filename or ":" in entry.filename:
            archive.close()
            raise ValueError("Unsafe archive member")
    return archive


def assemble(args: argparse.Namespace) -> dict:
    destination = args.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Destination must be absent or empty; existing payloads are never overwritten")
    destination.mkdir(parents=True, exist_ok=True)
    copy_files(args.apache_root, destination / "apache", APACHE_FILES)
    copy_files(args.mariadb_root, destination / "mariadb", MARIADB_FILES)
    charset_files = sorted((args.mariadb_root / "share/charsets").glob("*"))
    for file in charset_files:
        if file.is_file() and file.suffix.lower() in {".xml", ".conf"}:
            copy_files(args.mariadb_root, destination / "mariadb", (file.relative_to(args.mariadb_root).as_posix(),))
    with verified_zip(args.php_zip, PHP_SHA256) as archive:
        for name in PHP_FILES:
            archive.extract(name, destination / "php")
    for folder in (destination / "php", destination / "apache/bin"):
        for name in CRT_FILES:
            shutil.copyfile(args.mariadb_root / "bin" / name, folder / name)
    with verified_zip(args.joomla_zip, JOOMLA_SHA256) as archive:
        for entry in archive.infolist():
            if not entry.is_dir() and PurePosixPath(entry.filename).parts[0] in JOOMLA_ROOTS:
                archive.extract(entry, destination / "joomla-base")
    if not args.extension.is_file() or not zipfile.is_zipfile(args.extension):
        raise ValueError("A built Joomla extension ZIP is required")
    shutil.copyfile(args.extension, destination / "extension.zip")
    source = Path(__file__).resolve().parent
    shutil.copyfile(source / "manage.php", destination / "manage.php")
    shutil.copyfile(source / "README.md", destination / "README.md")
    binary_versions = {}
    for name, expected in (("apache/bin/httpd.exe", (2, 4, 65)), ("php/php.exe", (8, 4, 27)),
                           ("mariadb/bin/mariadbd.exe", (10, 11, 16))):
        actual = windows_file_version(destination / name)
        if actual[:3] != expected:
            raise ValueError(f"Pinned runtime version mismatch: {name}: {actual}")
        binary_versions[name] = ".".join(map(str, actual))
    files = []
    unresolved = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(destination).as_posix()
        row = {"path": rel, "bytes": path.stat().st_size, "sha256": digest(path)}
        if path.suffix.lower() in {".exe", ".dll", ".so"}:
            machine, imports = pe_imports(path)
            if machine != 0x8664:
                raise ValueError(f"Non-x64 runtime: {rel}")
            row["machine"] = "AMD64"
            row["imports"] = imports
            # Search only the private application's documented DLL directories.
            search = [path.parent, destination / "php", destination / "apache/bin", destination / "mariadb/bin"]
            for dependency in imports:
                if dependency.startswith(("api-ms-win-", "ext-ms-win-")) or dependency in SYSTEM_IMPORTS:
                    continue
                if not any(any(child.name.lower() == dependency for child in folder.iterdir()) for folder in search if folder.is_dir()):
                    unresolved.append({"image": rel, "dependency": dependency})
        files.append(row)
    if unresolved:
        raise ValueError("Unresolved private runtime imports: " + json.dumps(unresolved))
    manifest = {
        "schema_version": 1, "platform": "windows", "architecture": "x64",
        "source_sha": args.source_sha, "product_version": args.version,
        "components": {
            "apache": {"version": "2.4.65", "source": "selected installed Apache runtime files; hashes listed below"},
            "mariadb": {"version": "10.11.16", "source": "selected installed MariaDB runtime files; hashes listed below"},
            "php": {"version": "8.4.27", "build": "TS VS17 x64", "archive_sha256": PHP_SHA256,
                    "upstream": "https://downloads.php.net/~windows/releases/php-8.4.27-1-Win32-vs17-x64.zip"},
            "joomla": {"version": "6.2.0", "archive_sha256": JOOMLA_SHA256,
                       "upstream": "https://downloads.joomla.org/cms/joomla6/6-2-0/Joomla_6-2-0-Stable-Full_Package.zip?format=zip"},
        },
        "runtime_binding": {"php_handler": "apache2handler", "php_thread_safety": True,
                            "bind_address": "127.0.0.1", "minimum_os": "Windows 10 x64",
                            "required_environment": "Prepend web/php;web/apache/bin;web/mariadb/bin to child-process PATH only",
                            "database_authority": "Joomla uses MariaDB; kernel sports storage remains the explicitly selected SQLite backend"},
        "files": files, "unresolved_imports": [], "clean_machine_tested": False,
        "verified_binary_file_versions": binary_versions,
    }
    (destination / "payload-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"prepared": True, "files": len(files), "bytes": sum(row["bytes"] for row in files),
            "manifest_sha256": digest(destination / "payload-manifest.json"), "source_sha": args.source_sha}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--apache-root", type=Path, required=True)
    parser.add_argument("--mariadb-root", type=Path, required=True)
    parser.add_argument("--php-zip", type=Path, required=True)
    parser.add_argument("--joomla-zip", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if len(args.source_sha) != 40 or any(c not in "0123456789abcdef" for c in args.source_sha):
        parser.error("--source-sha must be a full lowercase Git SHA")
    print(json.dumps(assemble(args), indent=2))


if __name__ == "__main__":
    main()
