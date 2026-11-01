#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, fs, io::{Read, Write}, path::PathBuf, net::{SocketAddr, TcpStream}, time::Duration};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;
mod client_state;
mod external_target;

fn build_information() -> serde_json::Value {
    serde_json::json!({
        "version": env!("CARGO_PKG_VERSION"),
        "source_sha": option_env!("DRAGONHYDRA_SOURCE_SHA").unwrap_or("unversioned-development"),
        "source_content_sha256": option_env!("DRAGONHYDRA_SOURCE_CONTENT_SHA256").unwrap_or("unversioned-development"),
        "api_namespace": "/dragon/api/v1",
        "schema_version": 1,
        "architecture": "x86_64-pc-windows-msvc",
        "product": "DRAGONHYDRA CORE NEXT", "edition": "CORE NEXT", "identifier": "ai.dragonhydra.corenext.desktop"
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
    if port < 18800 { return Err("CORE NEXT requires its isolated endpoint".into()); }
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut connection = TcpStream::connect_timeout(&address, Duration::from_secs(2))
        .map_err(|_| "The configured local server is unavailable".to_string())?;
    connection.set_read_timeout(Some(Duration::from_secs(3))).map_err(|_| "Identity timeout unavailable")?;
    connection.set_write_timeout(Some(Duration::from_secs(3))).map_err(|_| "Identity timeout unavailable")?;
    let request = format!("GET /dragon/api/v1/system HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n");
    connection.write_all(request.as_bytes()).map_err(|_| "CORE NEXT identity check failed")?;
    let mut response = String::new();
    connection.take(1_048_576).read_to_string(&mut response).map_err(|_| "CORE NEXT identity response unavailable")?;
    let (headers, body) = response.split_once("\r\n\r\n").ok_or("CORE NEXT identity response invalid")?;
    if !headers.lines().next().is_some_and(|line| line.contains(" 200 ")) { return Err("CORE NEXT identity rejected".into()); }
    let identity: serde_json::Value = serde_json::from_str(body).map_err(|_| "CORE NEXT identity response invalid")?;
    let instance = &identity["installation"];
    let expected = state.parent().and_then(std::path::Path::parent).and_then(std::path::Path::file_name)
        .and_then(|value| value.to_str()).ok_or("CORE NEXT instance directory missing")?;
    if instance["product"] != "DRAGONHYDRA CORE NEXT" || instance["edition"] != "CORE NEXT" || instance["installation_id"] != expected {
        return Err("CORE NEXT server identity differs from this installation".into());
    }
    url.set_path("/");
    url.set_query(None);
    url.set_fragment(Some(&format!("token={token}")));
    Ok(url)
}

fn state_path() -> Result<PathBuf, String> {
    let executable = env::current_exe().ok();
    let lab = PathBuf::from(r"C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB");
    client_state::select(env::args().skip(1), executable.as_deref(), &lab)
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
    let target = state_path().and_then(connection).map(WebviewUrl::External)
        .unwrap_or_else(|_| WebviewUrl::App("index.html?client=unpaired".into()));
    let profile = profile_path();
    tauri::Builder::default()
        // The dashboard's target="_blank" links need an OS browser handoff;
        // WebView2 does not open them without an explicit native integration.
        .plugin(tauri_plugin_opener::init())
        .setup(move |app| {
            let opener = app.handle().clone();
            let mut window = WebviewWindowBuilder::new(app, "main", target)
                // Programmatic window.open (Administration) does not produce
                // an anchor click for the opener plugin's injected handler.
                .on_new_window(move |url, _features| {
                    let local_source = opener.get_webview_window("main")
                        .and_then(|window| window.url().ok())
                        .is_some_and(|source| source.scheme() == "http" &&
                            source.host_str() == Some("127.0.0.1") &&
                            source.username().is_empty() && source.password().is_none());
                    if local_source && external_target::allowed(url.scheme(), url.host_str(),
                        url.username(), url.password().is_some(), url.query(), url.fragment()) {
                        if opener.opener().open_url(url.as_str(), None::<&str>).is_err() {
                            eprintln!("The default browser could not open the requested web address.");
                        }
                    }
                    tauri::webview::NewWindowResponse::Deny
                })
                .title("DRAGONHYDRA CORE NEXT")
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
