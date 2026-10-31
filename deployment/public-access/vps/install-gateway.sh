#!/usr/bin/env bash
# Run on the actual authorized VPS; dry-run is the default. No package downloads,
# firewall changes, Windows application edits, or remote access are performed.
set -euo pipefail
script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
target_ip=''
key_file=''
apply=0
while (($#)); do
    case "$1" in
        --ip) target_ip=${2:?Actual public IPv4 required}; shift 2;;
        --public-key-file) key_file=${2:?Public SSH key file required}; shift 2;;
        --apply) apply=1; shift;;
        --help) printf '%s\n' 'Usage: install-gateway.sh --ip ACTUAL_PUBLIC_IPV4 --public-key-file /path/to/key.pub [--apply]'; exit 0;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2;;
    esac
done
if [[ -z "$target_ip" || "$target_ip" == VPS_PUBLIC_IP || -z "$key_file" ]]; then
    printf '%s\n' '{"status":"requires_configuration","deployed":false,"missing":["actual authorized public IPv4","Windows tunnel public-key file"]}'
    exit 0
fi
for dependency in python3 nginx sshd ssh-keygen systemctl getent install flock grep cut id date; do
    command -v "$dependency" >/dev/null || { printf 'Required installed capability missing: %s\n' "$dependency" >&2; exit 2; }
done
[[ -d /run/systemd/system ]] || { printf '%s\n' 'A running native systemd installation is required.' >&2; exit 2; }
ssh-keygen -l -f "$key_file" >/dev/null || { printf '%s\n' 'OpenSSH rejected the supplied public key file.' >&2; exit 2; }
output="$script_dir/generated/$target_ip"
python3 "$script_dir/render_vps.py" --ip "$target_ip" --public-key-file "$key_file" --output "$output"
if ((apply == 0)); then
    printf '%s\n' '{"status":"prepared_not_deployed","applied":false,"note":"Use --apply only on the authorized VPS after reviewing rendered files. No service or account changes made."}'
    exit 0
fi
[[ $EUID -eq 0 ]] || { printf '%s\n' '--apply requires the authorized VPS administrator.' >&2; exit 2; }
for dependency in useradd userdel chown cp rm; do
    command -v "$dependency" >/dev/null || { printf 'Required installed capability missing: %s\n' "$dependency" >&2; exit 2; }
done
[[ -d /etc/nginx/conf.d && -d /etc/ssh/sshd_config.d ]] || { printf '%s\n' 'This target must already use nginx conf.d and OpenSSH sshd_config.d includes.' >&2; exit 2; }
ssh_unit=''
if systemctl is-active --quiet ssh.service; then ssh_unit=ssh.service;
elif systemctl is-active --quiet sshd.service; then ssh_unit=sshd.service;
else printf '%s\n' 'The existing SSH service must already be active; it will not be replaced or restarted.' >&2; exit 2; fi
nginx -t
sshd -t
state="$script_dir/state"
install -d -m 700 "$state"
exec 9>"$state/apply.lock"
flock -n 9 || { printf '%s\n' 'Another DRAGONHYDRA gateway apply is in progress.' >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$state/$stamp-$$"
install -d -m 700 "$backup"
nginx_path=/etc/nginx/conf.d/dragonhydra-public.conf
sshd_path=/etc/ssh/sshd_config.d/99-dragonhydra-tunnel.conf
account=dragonhydra-tunnel
account_dir=/var/lib/dragonhydra/tunnel
key_path="$account_dir/.ssh/authorized_keys"
marker='# DRAGONHYDRA managed public gateway v1; preserve unrelated configuration.'
for directory in /var/lib/dragonhydra "$account_dir" "$account_dir/.ssh"; do
    [[ ! -L "$directory" ]] || { printf 'Refusing symlinked account path: %s\n' "$directory" >&2; exit 2; }
done
paths=("$nginx_path" "$sshd_path" "$key_path")
for path in "${paths[@]}"; do
    [[ ! -L "$path" ]] || { printf 'Refusing symlink target: %s\n' "$path" >&2; exit 2; }
    if [[ -e "$path" ]]; then
        IFS= read -r first_line <"$path"
        [[ "$first_line" == "$marker" ]] || { printf 'Existing file is not DRAGONHYDRA-owned: %s\n' "$path" >&2; exit 2; }
    fi
done
if getent passwd "$account" >/dev/null; then
    existing_home=$(getent passwd "$account" | cut -d: -f6)
    [[ "$existing_home" == "$account_dir" && -f "$account_dir/.dragonhydra-managed-account" ]] || { printf '%s\n' 'Existing account is not proven DRAGONHYDRA-owned; no account changed.' >&2; exit 2; }
fi
for index in "${!paths[@]}"; do
    if [[ -e "${paths[$index]}" ]]; then cp -p -- "${paths[$index]}" "$backup/$index.file"; else : >"$backup/$index.absent"; fi
done
created_account=0
nginx_was_active=0
systemctl is-active --quiet nginx.service && nginx_was_active=1
changed=0
committed=0
rollback() {
    code=$?
    if ((committed == 0 && changed == 1)); then
        for index in "${!paths[@]}"; do
            if [[ -f "$backup/$index.file" ]]; then cp -p -- "$backup/$index.file" "${paths[$index]}";
            elif [[ -f "$backup/$index.absent" ]]; then rm -f -- "${paths[$index]}"; fi
        done
        if nginx -t >/dev/null 2>&1; then
            if ((nginx_was_active)); then systemctl reload nginx.service || true;
            else systemctl stop nginx.service || true; fi
        fi
        if sshd -t >/dev/null 2>&1; then systemctl reload "$ssh_unit" || true; fi
        if ((created_account)); then userdel "$account" || true; rm -f -- "$account_dir/.dragonhydra-managed-account"; fi
        printf 'Apply failed; only owned files were restored from %s\n' "$backup" >&2
    fi
    exit "$code"
}
trap rollback EXIT
changed=1
if ! getent passwd "$account" >/dev/null; then
    useradd --system --create-home --home-dir "$account_dir" --shell /usr/sbin/nologin "$account"
    created_account=1
    printf '%s\n' "$marker" >"$account_dir/.dragonhydra-managed-account"
fi
install -d -m 700 -o "$account" -g "$(id -gn "$account")" "$account_dir/.ssh"
install -m 600 -o "$account" -g "$(id -gn "$account")" "$output/authorized_keys" "$key_path"
install -m 644 -o root -g root "$output/dragonhydra-public.conf" "$nginx_path"
install -m 644 -o root -g root "$output/99-dragonhydra-tunnel.conf" "$sshd_path"
install -d -m 755 -o root -g root /var/lib/dragonhydra/acme
# Validate the complete configuration, including existing files, before reload.
nginx -t
sshd -t
effective_sshd=$(sshd -T -C "user=$account,host=$target_ip,addr=127.0.0.1")
for required in 'allowtcpforwarding remote' 'gatewayports no' 'permitlisten 127.0.0.1:18080' 'permittty no' 'forcecommand /bin/false' 'authenticationmethods publickey'; do
    grep -Fxq "$required" <<<"$effective_sshd" || { printf 'Effective SSH restriction missing: %s\n' "$required" >&2; exit 1; }
done
unset effective_sshd
effective_nginx=$(nginx -T 2>&1)
[[ "$effective_nginx" == *"# configuration file $nginx_path:"* ]] || { printf '%s\n' 'The existing nginx configuration did not include the staged owned file.' >&2; exit 1; }
unset effective_nginx
systemctl reload "$ssh_unit"
if ((nginx_was_active)); then systemctl reload nginx.service; else systemctl start nginx.service; fi
committed=1
printf '{"status":"applied","public_ip":"%s","http_url":"http://%s/","domain_required":false,"certificate_required":false,"backup":"%s","note":"Verify the Windows outbound tunnel and external reachability separately; no firewall was changed."}\n' "$target_ip" "$target_ip" "$backup"
