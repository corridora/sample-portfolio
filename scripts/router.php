<?php
$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);
if ($path!=='/' && is_file(dirname(__DIR__).'/public'.$path) && realpath(dirname(__DIR__).'/public'.$path) && str_starts_with(realpath(dirname(__DIR__).'/public'.$path),dirname(__DIR__).'/public/')) return false;
require dirname(__DIR__).'/public/index.php';
