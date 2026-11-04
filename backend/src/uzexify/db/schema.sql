CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DROP VIEW IF EXISTS v_deals CASCADE;
DROP TABLE IF EXISTS deals, products, contracts, participants, brokers, usd_rates, regions CASCADE;
CREATE TABLE regions (name_uz text PRIMARY KEY, name_ru text UNIQUE NOT NULL);
CREATE TABLE participants (inn text PRIMARY KEY, name text NOT NULL, region_uz text REFERENCES regions(name_uz), activity text, role text, vat_payer boolean, name_key text, n_deals_sold integer DEFAULT 0, n_deals_bought integer DEFAULT 0);
CREATE TABLE brokers (code text PRIMARY KEY, name text NOT NULL, inn text, region_uz text REFERENCES regions(name_uz), name_key text, n_deals integer DEFAULT 0);
CREATE TABLE contracts (contract_no text PRIMARY KEY, product_name text, brand text, size text, grade text, product_type text, product_class text, tnved_code text, product_group text, product_category text, industry text, unit text, lot_size numeric, currency text, base_price numeric, deposit_pct numeric, delivery_basis text, region_ru text, region_uz text REFERENCES regions(name_uz), warehouse_address text, trade_type text, contract_type text, contract_form text, payment_term_days integer, delivery_term_days integer, packaging text, seller_inn text REFERENCES participants(inn), registered_on date, valid_until date);
CREATE TABLE usd_rates (rate_date date PRIMARY KEY, uzs_per_usd numeric NOT NULL);
CREATE TABLE deals (deal_no bigint PRIMARY KEY, deal_date date, deal_time time, trade_type text, quantity_lots numeric, amount numeric, start_price numeric, contract_no text REFERENCES contracts(contract_no), product text, lot_size numeric, unit text, region_uz text REFERENCES regions(name_uz), contract_type text, contract_form text, status text, seller_inn text REFERENCES participants(inn), buyer_inn text REFERENCES participants(inn), seller_broker text REFERENCES brokers(code), buyer_broker text REFERENCES brokers(code), paid_on date, delivered_on date, delivered_lots numeric);
CREATE TABLE products (product text PRIMARY KEY, product_name text, product_category text, industry text, unit text, n_deals integer, first_deal date, last_deal date, name_key text, embedding vector, embedding_model text);
CREATE INDEX ON deals(deal_date);
CREATE INDEX ON deals(contract_no);
CREATE INDEX ON deals(seller_inn);
CREATE INDEX ON deals(buyer_inn);
CREATE INDEX ON deals(product);
CREATE INDEX ON deals(status);
CREATE VIEW v_deals AS
SELECT d.*, c.product_name, c.product_category, c.product_group, c.industry, c.currency, c.tnved_code,
 d.quantity_lots * d.lot_size AS volume,
 d.amount / NULLIF(d.quantity_lots * d.lot_size, 0) AS unit_price,
 r.uzs_per_usd AS usd_rate,
 CASE WHEN c.currency = 'Доллар США' THEN d.amount * r.uzs_per_usd ELSE d.amount END AS amount_uzs,
 CASE WHEN c.currency = 'Доллар США' THEN d.amount ELSE d.amount / NULLIF(r.uzs_per_usd, 0) END AS amount_usd,
 seller.name AS seller_name, buyer.name AS buyer_name, sb.name AS seller_broker_name, bb.name AS buyer_broker_name, reg.name_ru AS region_ru
FROM deals d JOIN contracts c USING (contract_no)
LEFT JOIN usd_rates r ON r.rate_date = d.deal_date
LEFT JOIN participants seller ON seller.inn = d.seller_inn
LEFT JOIN participants buyer ON buyer.inn = d.buyer_inn
LEFT JOIN brokers sb ON sb.code = d.seller_broker
LEFT JOIN brokers bb ON bb.code = d.buyer_broker
LEFT JOIN regions reg ON reg.name_uz = d.region_uz;
