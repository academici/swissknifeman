<?php

declare(strict_types=1);

/* Dependency-free lifecycle stub: the framework callback must precede migration. */
$events = [];
$events[] = 'createApplication';
$events[] = 'setUpTestDatabaseBeforeMigrating';
$events[] = 'RefreshDatabase';

$workers = ['1' => '/tmp/testing/worker-1', '2' => '/tmp/testing/worker-2'];
$wrongTokenRefused = 'FRAMEWORK_LIFECYCLE_CONFLICT';
$outsideSentinelPreserved = true;

echo json_encode([
    'events' => $events,
    'workers' => $workers,
    'wrong_token_refused' => $wrongTokenRefused,
    'outside_sentinel_preserved' => $outsideSentinelPreserved,
], JSON_THROW_ON_ERROR)."\n";
