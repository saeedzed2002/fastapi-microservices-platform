CREATE ROLE inventory_service LOGIN PASSWORD 'inventory-local-only';
CREATE DATABASE inventory_service OWNER inventory_service;

CREATE ROLE cart_service LOGIN PASSWORD 'cart-local-only';
CREATE DATABASE cart_service OWNER cart_service;
