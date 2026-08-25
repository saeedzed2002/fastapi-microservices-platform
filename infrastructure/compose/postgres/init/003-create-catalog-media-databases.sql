CREATE ROLE catalog_service LOGIN PASSWORD 'catalog-local-only';
CREATE DATABASE catalog_service OWNER catalog_service;

CREATE ROLE media_service LOGIN PASSWORD 'media-local-only';
CREATE DATABASE media_service OWNER media_service;
