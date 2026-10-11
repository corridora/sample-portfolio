<?php
declare(strict_types=1);
namespace App;

final class Settings
{
    public static function load(): void
    {
        foreach (['config', 'secrets'] as $name) {
            $path = dirname(__DIR__)."/.sample/$name.json";
            if (is_file($path)) {
                foreach (json_decode(file_get_contents($path), true, 64, JSON_THROW_ON_ERROR) as $key => $value) {
                    if (getenv($key) === false) putenv($key.'='.(is_bool($value) ? ($value ? 'true' : 'false') : $value));
                }
            }
        }
    }
    public static function get(string $name, string $default = ''): string { return getenv($name) !== false ? (string)getenv($name) : $default; }
    public static function enabled(string $name): bool { return self::get($name) === 'true'; }
    public static function version(): string { return self::get('SERVICE_VERSION', is_file(dirname(__DIR__).'/BUILD_VERSION') ? trim(file_get_contents(dirname(__DIR__).'/BUILD_VERSION')) : 'local'); }
}
