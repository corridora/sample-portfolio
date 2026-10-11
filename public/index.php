<?php
declare(strict_types=1);
require dirname(__DIR__).'/vendor/autoload.php';
\App\Settings::load();
foreach (['storage/framework/views','storage/framework/cache','storage/logs','bootstrap/cache'] as $dir) if (!is_dir(dirname(__DIR__).'/'.$dir)) mkdir(dirname(__DIR__).'/'.$dir,0750,true);
$app=require dirname(__DIR__).'/bootstrap/app.php';
$app->singleton(\App\Store::class);
$app->handleRequest(\Illuminate\Http\Request::capture());
