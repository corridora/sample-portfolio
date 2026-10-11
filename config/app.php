<?php
return ['name'=>'Corridora Portfolio','env'=>getenv('DEPLOYMENT_ENVIRONMENT')?:'local','debug'=>false,'url'=>getenv('APP_URL')?:'http://127.0.0.1:4105','timezone'=>'UTC','locale'=>'en','fallback_locale'=>'en','key'=>getenv('APP_KEY')?:'base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=','cipher'=>'AES-256-CBC'];
