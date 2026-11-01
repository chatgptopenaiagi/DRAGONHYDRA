//! Select only the explicitly requested or corresponding installed workstation.
//! Pairing files remain owned by the workstation; discovery never creates them.
use std::{collections::BTreeMap, fs, path::{Path, PathBuf}};

fn product_marker(path: &Path) -> Result<BTreeMap<String, String>, String> {
    if !path.is_file() || fs::metadata(path).map_err(|_| "Installation binding is unavailable")?.len() > 16_384 {
        return Err("Installation binding is invalid".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        #[link(name = "kernel32")]
        extern "system" {
            fn GetPrivateProfileStringW(section: *const u16, key: *const u16,
                default_value: *const u16, output: *mut u16, size: u32,
                filename: *const u16) -> u32;
        }
        // Use the Windows INI API, matching NSIS WriteINIStr, so non-ASCII
        // installation paths also work with its ANSI/UTF-16 file encodings.
        let filename: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        let section: Vec<u16> = "Product".encode_utf16().chain(Some(0)).collect();
        let mut result = BTreeMap::new();
        for name in ["Identity", "InstallRoot", "StateRoot"] {
            let key: Vec<u16> = name.encode_utf16().chain(Some(0)).collect();
            let mut output = vec![0u16; 4096];
            let count = unsafe { GetPrivateProfileStringW(section.as_ptr(), key.as_ptr(),
                std::ptr::null(), output.as_mut_ptr(), output.len() as u32, filename.as_ptr()) } as usize;
            if count == 0 || count >= output.len() - 1 {
                return Err("Installation binding is incomplete".into());
            }
            result.insert(name.to_string(), String::from_utf16(&output[..count])
                .map_err(|_| "Installation binding is invalid")?);
        }
        Ok(result)
    }
    #[cfg(not(windows))]
    {
        let text = fs::read_to_string(path).map_err(|_| "Installation binding is invalid")?;
        let mut section = false;
        let mut result = BTreeMap::new();
        for line in text.lines().map(str::trim) {
            if line.starts_with('[') { section = line == "[Product]"; }
            else if section {
                if let Some((key, value)) = line.split_once('=') {
                    result.insert(key.trim().into(), value.trim().into());
                }
            }
        }
        Ok(result)
    }
}

pub fn select(args: impl IntoIterator<Item = String>, executable: Option<&Path>,
              program_data: &Path) -> Result<PathBuf, String> {
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if let Some(value) = arg.strip_prefix("--state=") { return Ok(PathBuf::from(value)); }
        if arg == "--state" { return Ok(PathBuf::from(args.next().unwrap_or_default())); }
    }
    if let Some(client) = executable.and_then(Path::parent) {
        if client.file_name().is_some_and(|name| name.to_string_lossy().eq_ignore_ascii_case("client")) {
            if let Some(install_root) = client.parent() {
                let marker = install_root.join("workstation").join("installer.ini");
                if marker.exists() {
                    let binding = product_marker(&marker)?;
                    let recorded_root = binding.get("InstallRoot").ok_or("Installation root is missing")?;
                    let recorded_state = binding.get("StateRoot").ok_or("Installation state is missing")?;
                    let recorded_root = PathBuf::from(recorded_root);
                    let state = PathBuf::from(recorded_state);
                    if binding.get("Identity").map(String::as_str) != Some("DRAGONHYDRA CORE NEXT v1")
                        || !recorded_root.is_absolute() || !state.is_absolute() {
                        return Err("Installation binding is invalid".into());
                    }
                    let actual = fs::canonicalize(install_root).map_err(|_| "Installation root is unavailable")?;
                    let recorded = fs::canonicalize(recorded_root).map_err(|_| "Installation root is unavailable")?;
                    let same_root = if cfg!(windows) {
                        actual.to_string_lossy().eq_ignore_ascii_case(&recorded.to_string_lossy())
                    } else { actual == recorded };
                    if !same_root { return Err("Installation binding belongs to another workstation".into()); }
                    // Do not fall back to another profile when this installation
                    // is stopped or has not yet published its pairing metadata.
                    return Ok(state.join("client"));
                }
            }
        }
    }
    let _ = program_data;
    Err("CORE NEXT requires its explicit state or corresponding installation marker".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let suffix = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
            let root = std::env::temp_dir().join(format!("dragonhydra-client-state-{}-{suffix}", std::process::id()));
            fs::create_dir_all(root.join("installed/client")).unwrap();
            fs::create_dir_all(root.join("installed/workstation")).unwrap();
            Self(root)
        }
        fn exe(&self) -> PathBuf { self.0.join("installed/client/DRAGONHYDRA-Client.exe") }
        fn marker(&self, identity: &str, root: &Path, state: &Path) {
            fs::write(self.0.join("installed/workstation/installer.ini"), format!(
                "[Product]\nIdentity={identity}\nInstallRoot={}\nStateRoot={}\n", root.display(), state.display())).unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            // Verify the resolved, explicitly created fixture before recursive
            // cleanup; never follow a redirected or unrelated computed target.
            if let (Ok(target), Ok(temporary)) = (fs::canonicalize(&self.0), fs::canonicalize(std::env::temp_dir())) {
                if target.parent() == Some(temporary.as_path()) && target.file_name()
                    .is_some_and(|name| name.to_string_lossy().starts_with("dragonhydra-client-state-")) {
                    let _ = fs::remove_dir_all(target);
                }
            }
        }
    }

    #[test]
    fn bare_executable_requires_explicit_profile() {
        let base = std::env::temp_dir();
        assert!(select(Vec::new(), None, &base).is_err());
    }
    #[test]
    fn explicit_state_remains_exact_for_both_argument_forms() {
        let base = std::env::temp_dir();
        for args in [vec!["--state".into(), "custom state".into()], vec!["--state=custom state".into()]] {
            assert_eq!(select(args, None, &base).unwrap(), PathBuf::from("custom state"));
        }
    }
    #[test]
    fn installed_executable_selects_its_own_state_even_before_pairing_exists() {
        let f = Fixture::new(); let state = f.0.join("state with spaces");
        f.marker("DRAGONHYDRA CORE NEXT v1", &f.0.join("installed"), &state);
        assert_eq!(select(Vec::new(), Some(&f.exe()), &f.0).unwrap(), state.join("client"));
        assert!(!state.exists());
    }
    #[test]
    fn unrelated_or_malformed_installation_never_falls_back_to_default_profile() {
        let f = Fixture::new(); let state = f.0.join("private state");
        f.marker("another application", &f.0.join("installed"), &state);
        assert!(select(Vec::new(), Some(&f.exe()), &f.0).is_err());
        f.marker("DRAGONHYDRA CORE NEXT v1", &f.0, &state);
        assert!(select(Vec::new(), Some(&f.exe()), &f.0).is_err());
        f.marker("DRAGONHYDRA CORE NEXT v1", &f.0.join("installed"), Path::new("relative state"));
        assert!(select(Vec::new(), Some(&f.exe()), &f.0).is_err());
    }
    #[test]
    fn explicit_state_wins_over_malformed_nearby_marker() {
        let f = Fixture::new();
        f.marker("another application", &f.0, &f.0);
        assert_eq!(select(vec!["--state=explicit".into()], Some(&f.exe()), &f.0).unwrap(), PathBuf::from("explicit"));
    }
    #[test]
    fn metadata_in_working_directory_does_not_rebind_a_portable_executable() {
        let f = Fixture::new();
        f.marker("DRAGONHYDRA CORE NEXT v1", &f.0.join("installed"), &f.0.join("other state"));
        assert!(select(Vec::new(), Some(&f.0.join("portable.exe")), &f.0).is_err());
    }
    #[cfg(windows)]
    #[test]
    fn windows_ini_unicode_state_path_is_preserved() {
        let f = Fixture::new(); let state = f.0.join("state \u{0394}");
        let text = format!("[Product]\r\nIdentity=DRAGONHYDRA CORE NEXT v1\r\nInstallRoot={}\r\nStateRoot={}\r\n",
                           f.0.join("installed").display(), state.display());
        let bytes: Vec<u8> = std::iter::once(0xfeffu16).chain(text.encode_utf16())
            .flat_map(u16::to_le_bytes).collect();
        fs::write(f.0.join("installed/workstation/installer.ini"), bytes).unwrap();
        assert_eq!(select(Vec::new(), Some(&f.exe()), &f.0).unwrap(), state.join("client"));
    }
}
