#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, fs, path::PathBuf, net::{SocketAddr, TcpStream}, time::Duration};
use tauri::{WebviewUrl, WebviewWindowBuilder};

fn build_information() -> serde_json::Value {
    serde_json::json!({
        "version": env!("CARGO_PKG_VERSION"),
        "source_sha": option_env!("DRAGONHYDRA_SOURCE_SHA").unwrap_or("unversioned-development"),
        "api_namespace": "/dragon/api/v1",
        "schema_version": 1,
        "architecture": "x86_64-pc-windows-msvc"
    })
}

fn read_json(path: PathBuf) -> Result<serde_json::Value, String> {
    let data = fs::read_to_string(path).map_err(|_| "Product state is unavailable".to_string())?;
    serde_json::from_str(&data).map_err(|_| "Product state is invalid".to_string())
}

fn connection(state: PathBuf) -> Result<tauri::Url, String> {
    let endpoint = read_json(state.join("endpoint.json"))?;
    let session = read_json(state.join("local-session.json"))?;
    let mut url: tauri::Url = endpoint["url"].as_str().ok_or("Endpoint is missing")?.parse().map_err(|_| "Endpoint is invalid")?;
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") || url.username() != "" || url.password().is_some() {
        return Err("This local client requires an explicit loopback product endpoint".to_string());
    }
    let token = session["token"].as_str().ok_or("Local pairing is missing")?;
    if !token.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_') || token.len() < 20 {
        return Err("Local pairing is invalid".to_string());
    }
    let port = url.port_or_known_default().ok_or("Endpoint port is missing")?;
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_secs(2))
        .map_err(|_| "The configured local server is unavailable".to_string())?;
    url.set_path("/");
    url.set_query(None);
    url.set_fragment(Some(&format!("token={token}")));
    Ok(url)
}

fn state_path() -> PathBuf {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if let Some(path) = arg.strip_prefix("--state=") { return PathBuf::from(path); }
        if arg == "--state" { return PathBuf::from(args.next().unwrap_or_default()); }
    }
    PathBuf::from(env::var("PROGRAMDATA").unwrap_or_else(|_| "/var/lib".to_string())).join("DRAGONHYDRA")
}

fn profile_path() -> Option<PathBuf> {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if let Some(path) = arg.strip_prefix("--profile=") { return Some(PathBuf::from(path)); }
        if arg == "--profile" { return args.next().map(PathBuf::from); }
    }
    None
}

fn main() {
    // An engineering-only, read-only probe of constants compiled into this exact
    // binary. It neither starts a webview nor exposes a native browser command.
    if env::args().any(|arg| arg == "--build-info") {
        println!("{}", build_information());
        return;
    }
    let target = connection(state_path()).map(WebviewUrl::External)
        .unwrap_or_else(|_| WebviewUrl::App("index.html?client=unpaired".into()));
    let profile = profile_path();
    tauri::Builder::default()
        .setup(move |app| {
            let mut window = WebviewWindowBuilder::new(app, "main", target)
                .title("DRAGONHYDRA")
                .inner_size(1280.0, 860.0)
                .min_inner_size(720.0, 520.0);
            if let Some(directory) = profile {
                window = window.data_directory(directory);
            }
            window.build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("DRAGONHYDRA could not start its desktop window");
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_state_is_bounded() { assert!(connection(PathBuf::from("missing-product-test-state")).is_err()); }
}
