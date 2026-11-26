Real local IO and infrastructure subprocess diagnostics. PostgreSQL tests use
only SKM_TEST_DATABASE_URL, skip locally when absent and fail in required mode.
The initial connection smoke executes SELECT 1 without tables or migrations.
