<?php
declare(strict_types=1);
namespace App;

final class Store
{
    public readonly \PDO $db;
    public function __construct()
    {
        $file=Settings::get('PORTFOLIO_DB',dirname(__DIR__).'/storage/portfolio.sqlite');
        $this->db=new \PDO('sqlite:'.$file,null,null,[\PDO::ATTR_ERRMODE=>\PDO::ERRMODE_EXCEPTION]);
        $this->db->exec('PRAGMA busy_timeout=3000; PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS holdings (symbol TEXT PRIMARY KEY, shares REAL NOT NULL); CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT NOT NULL)');
        foreach (['DEMO'=>12,'CLOUD'=>30,'TRACE'=>8] as $symbol=>$shares) {
            $s=$this->db->prepare('INSERT OR IGNORE INTO holdings VALUES (?,?)'); $s->execute([$symbol,$shares]);
        }
    }
    public function get(string $name): ?array
    {
        $s=$this->db->prepare('SELECT value FROM state WHERE name=?'); $s->execute([$name]); $raw=$s->fetchColumn();
        return $raw===false?null:json_decode($raw,true,32,JSON_THROW_ON_ERROR);
    }
    public function put(string $name,array $value): void
    {
        $s=$this->db->prepare('INSERT INTO state(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value'); $s->execute([$name,json_encode($value,JSON_THROW_ON_ERROR)]);
    }
}
