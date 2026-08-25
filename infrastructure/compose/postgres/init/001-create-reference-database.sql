CREATE USER reference_service WITH PASSWORD 'reference-local-only';
CREATE DATABASE reference_service OWNER reference_service;
REVOKE ALL ON DATABASE reference_service FROM PUBLIC;
GRANT CONNECT ON DATABASE reference_service TO reference_service;
