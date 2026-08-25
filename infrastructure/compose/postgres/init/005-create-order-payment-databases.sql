CREATE ROLE order_service LOGIN PASSWORD 'order-local-only';
CREATE DATABASE order_service OWNER order_service;
CREATE ROLE payment_service LOGIN PASSWORD 'payment-local-only';
CREATE DATABASE payment_service OWNER payment_service;
