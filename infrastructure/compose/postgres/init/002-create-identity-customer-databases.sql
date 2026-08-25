CREATE USER identity_service WITH PASSWORD 'identity-local-only';
CREATE DATABASE identity_service OWNER identity_service;
REVOKE ALL ON DATABASE identity_service FROM PUBLIC;
GRANT CONNECT ON DATABASE identity_service TO identity_service;

CREATE USER customer_service WITH PASSWORD 'customer-local-only';
CREATE DATABASE customer_service OWNER customer_service;
REVOKE ALL ON DATABASE customer_service FROM PUBLIC;
GRANT CONNECT ON DATABASE customer_service TO customer_service;
