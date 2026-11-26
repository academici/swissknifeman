-- Runs once on an empty dev volume; also reapplied by make db-reset.
CREATE DATABASE skm_dev;
CREATE DATABASE skm_test;
-- In development the superuser skm owns both databases.
\connect skm_dev
CREATE EXTENSION IF NOT EXISTS pgcrypto;
\connect skm_test
CREATE EXTENSION IF NOT EXISTS pgcrypto;
