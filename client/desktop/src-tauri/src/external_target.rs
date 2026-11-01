//! Restrict native window.open handoffs to credential-free web addresses.
fn sensitive_key(value: &str) -> bool {
    let encoded = value.as_bytes();
    let mut decoded = Vec::new();
    let mut index = 0;
    while index < encoded.len() {
        if encoded[index] == b'%' && index + 2 < encoded.len() {
            if let Ok(pair) = std::str::from_utf8(&encoded[index + 1..index + 3]) {
                if let Ok(byte) = u8::from_str_radix(pair, 16) {
                    decoded.push(byte); index += 3; continue;
                }
            }
        }
        decoded.push(encoded[index]); index += 1;
    }
    let key: String = String::from_utf8_lossy(&decoded).chars()
        .filter(|c| *c != '_' && *c != '-').flat_map(char::to_lowercase).collect();
    matches!(key.as_str(), "token" | "accesstoken" | "apikey" | "apitoken" | "key" |
             "password" | "secret" | "authorization")
}

pub fn allowed(scheme: &str, host: Option<&str>, username: &str, password: bool,
               query: Option<&str>, fragment: Option<&str>) -> bool {
    let web = scheme == "https" || (scheme == "http" &&
        matches!(host, Some("127.0.0.1" | "localhost" | "[::1]" | "::1")));
    web && host.is_some() && username.is_empty() && !password &&
        !query.into_iter().chain(fragment).flat_map(|part| part.split('&'))
            .any(|part| sensitive_key(part.split('=').next().unwrap_or_default()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_provider_https_and_local_administration_are_allowed() {
        assert!(allowed("https", Some("www.api-football.com"), "", false, None, Some("section/Introduction")));
        assert!(allowed("https", Some("docs.sportmonks.com"), "", false, Some("page=1"), None));
        assert!(allowed("http", Some("127.0.0.1"), "", false, None, None));
    }
    #[test]
    fn non_web_cleartext_remote_or_embedded_credentials_are_rejected() {
        for scheme in ["file", "javascript", "data", "cmd", "mailto"] {
            assert!(!allowed(scheme, Some("example.test"), "", false, None, None));
        }
        assert!(!allowed("http", Some("example.test"), "", false, None, None));
        assert!(!allowed("https", Some("example.test"), "user", false, None, None));
        assert!(!allowed("https", Some("example.test"), "", true, None, None));
    }
    #[test]
    fn pairing_and_api_credentials_never_reach_the_browser() {
        for parameters in ["token=private", "api_key=private", "API-KEY=private", "%74oken=private", "access_token=private"] {
            assert!(!allowed("https", Some("example.test"), "", false, Some(parameters), None));
            assert!(!allowed("https", Some("example.test"), "", false, None, Some(parameters)));
        }
    }
}
