<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service;
defined('_JEXEC') or die;

/** Bounded loopback transport. Identity is signed server-side, never supplied by a browser. */
final class ApiClient
{
    public function __construct(
        private string $base,
        private string $secret,
        private string $user,
        private string $roles,
    ) {
        self::validateBase($base);
        if (strlen($secret) < 32) {
            throw new \RuntimeException('BRIDGE_NOT_CONFIGURED: Configure the protected bridge-secret file in component options.');
        }
        if (!preg_match('/^joomla:[0-9]+$/D', $user) || !in_array($roles, ['admin', 'reader'], true)) {
            throw new \RuntimeException('INVALID_BRIDGE_IDENTITY');
        }
    }

    public static function validateBase(string $base): void
    {
        $parts = parse_url($base);
        if (!$parts || !in_array($parts['scheme'] ?? '', ['http', 'https'], true)
            || !in_array(strtolower($parts['host'] ?? ''), ['127.0.0.1', '[::1]'], true)
            || rtrim($parts['path'] ?? '', '/') !== '/dragon/api/v1'
            || isset($parts['user']) || isset($parts['pass']) || isset($parts['query']) || isset($parts['fragment'])) {
            throw new \RuntimeException('INVALID_API_ENDPOINT: Use the product loopback address and /dragon/api/v1.');
        }
    }

    public static function signature(string $secret, string $method, string $path, string $time, string $nonce, string $user, string $roles, string $body): string
    {
        return hash_hmac('sha256', implode("\n", [$method, $path, $time, $nonce, $user, $roles, hash('sha256', $body)]), $secret);
    }

    public function request(string $method, string $path, ?array $payload = null): array
    {
        if (!in_array($method, ['GET', 'POST'], true) || !preg_match('~^/[A-Za-z0-9_/?=&%.,:-]+$~D', $path)
            || str_contains($path, '..') || str_starts_with($path, '//')) {
            throw new \RuntimeException('INVALID_KERNEL_OPERATION');
        }
        $body = $payload === null ? '' : json_encode((object) $payload, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
        $time = (string) time();
        $nonce = bin2hex(random_bytes(16));
        $signedPath = '/dragon/api/v1' . $path;
        $headers = [
            'Accept: application/json', 'Content-Type: application/json',
            'X-Dragon-User: ' . $this->user, 'X-Dragon-Roles: ' . $this->roles,
            'X-Dragon-Time: ' . $time, 'X-Dragon-Nonce: ' . $nonce,
            'X-Dragon-Signature: ' . self::signature($this->secret, $method, $signedPath, $time, $nonce, $this->user, $this->roles, $body),
        ];
        $response = '';
        $handle = curl_init(rtrim($this->base, '/') . $path);
        curl_setopt_array($handle, [
            CURLOPT_CUSTOMREQUEST => $method, CURLOPT_HTTPHEADER => $headers,
            CURLOPT_CONNECTTIMEOUT => 3, CURLOPT_TIMEOUT => 12,
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_MAXREDIRS => 0,
            CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_PROXY => '',
            CURLOPT_WRITEFUNCTION => static function ($handle, string $part) use (&$response): int {
                if (strlen($response) + strlen($part) > 2 * 1024 * 1024) {
                    return 0;
                }
                $response .= $part;
                return strlen($part);
            },
        ]);
        if ($method === 'POST') {
            curl_setopt($handle, CURLOPT_POSTFIELDS, $body);
        }
        if (curl_exec($handle) === false) {
            curl_close($handle);
            throw new \RuntimeException('KERNEL_UNREACHABLE: The API did not respond within its bounded request. Cached kernel data is retained.');
        }
        $status = curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
        curl_close($handle);
        try {
            $data = json_decode($response, true, 64, JSON_THROW_ON_ERROR);
        } catch (\JsonException $error) {
            throw new \RuntimeException('INVALID_KERNEL_RESPONSE');
        }
        if (!is_array($data)) {
            throw new \RuntimeException('INVALID_KERNEL_RESPONSE');
        }
        if ($status < 200 || $status >= 300) {
            $code = preg_replace('/[^A-Z0-9_]/', '', (string) ($data['error']['code'] ?? 'KERNEL_REQUEST_FAILED'));
            throw new \RuntimeException($code . ': Kernel request failed (HTTP ' . $status . ').');
        }
        return $data;
    }

    /** Download only a completed, identity-owned export through the same signed bridge. */
    public function download(string $path): array
    {
        if (!preg_match('~^/exports/([a-f0-9]{32})/download$~D', $path, $match)) {
            throw new \RuntimeException('INVALID_EXPORT_DOWNLOAD');
        }
        $time = (string) time();
        $nonce = bin2hex(random_bytes(16));
        $signedPath = '/dragon/api/v1' . $path;
        $response = '';
        $filename = '';
        $handle = curl_init(rtrim($this->base, '/') . $path);
        curl_setopt_array($handle, [
            CURLOPT_HTTPHEADER => [
                'X-Dragon-User: ' . $this->user, 'X-Dragon-Roles: ' . $this->roles,
                'X-Dragon-Time: ' . $time, 'X-Dragon-Nonce: ' . $nonce,
                'X-Dragon-Signature: ' . self::signature($this->secret, 'GET', $signedPath, $time, $nonce, $this->user, $this->roles, ''),
            ],
            CURLOPT_CONNECTTIMEOUT => 3, CURLOPT_TIMEOUT => 15,
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_MAXREDIRS => 0,
            CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_PROXY => '',
            CURLOPT_HEADERFUNCTION => static function ($handle, string $line) use (&$filename): int {
                if (preg_match('/^Content-Disposition:\s*attachment;\s*filename="?([a-f0-9]{32}\.(?:xlsx|json|csv))"?\s*$/iD', trim($line), $found)) {
                    $filename = $found[1];
                }
                return strlen($line);
            },
            CURLOPT_WRITEFUNCTION => static function ($handle, string $part) use (&$response): int {
                if (strlen($response) + strlen($part) > 8 * 1024 * 1024) {
                    return 0;
                }
                $response .= $part;
                return strlen($part);
            },
        ]);
        $completed = curl_exec($handle);
        $status = curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
        curl_close($handle);
        if ($completed === false) {
            throw new \RuntimeException('EXPORT_DOWNLOAD_UNAVAILABLE');
        }
        if ($status !== 200 || !$filename || !str_starts_with($filename, $match[1] . '.')) {
            throw new \RuntimeException('EXPORT_DOWNLOAD_NOT_READY_OR_DENIED');
        }
        $extension = pathinfo($filename, PATHINFO_EXTENSION);
        $types = ['json' => 'application/json', 'csv' => 'text/csv; charset=utf-8',
                  'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
        return ['body' => $response, 'filename' => $filename, 'content_type' => $types[$extension]];
    }
}
