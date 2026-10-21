-- Generated from design: enterprise-voice-agent-data-design-v1.md (v1)
-- Supporting design: tool-platform-enterprise-systems-integration-design-v1.md (v1)
-- Ticket: none
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.customer (
  customer_id TEXT PRIMARY KEY CHECK (customer_id ~ '^CU-[0-9]+$'),
  full_name TEXT NOT NULL,
  mobile_e164 TEXT NOT NULL,
  kyc_status TEXT NOT NULL CHECK (kyc_status IN ('VERIFIED','PENDING','FAILED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS core.loan (
  loan_id TEXT PRIMARY KEY CHECK (loan_id ~ '^LN-[0-9]+$'),
  customer_id TEXT NOT NULL REFERENCES core.customer(customer_id) ON DELETE RESTRICT,
  product_code TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','CLOSED','FORECLOSED','DELINQUENT')),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  sanctioned_amount NUMERIC(14,2) NOT NULL CHECK (sanctioned_amount > 0),
  outstanding_principal NUMERIC(14,2) NOT NULL CHECK (outstanding_principal >= 0),
  annual_rate_percent NUMERIC(5,2) NOT NULL CHECK (annual_rate_percent >= 0),
  rate_type TEXT NOT NULL CHECK (rate_type IN ('FIXED','FLOATING')),
  emi_amount NUMERIC(14,2) NOT NULL CHECK (emi_amount > 0),
  previous_emi NUMERIC(14,2) NOT NULL CHECK (previous_emi > 0),
  next_due_at TIMESTAMPTZ,
  tenure_remaining_months INTEGER NOT NULL CHECK (tenure_remaining_months >= 0),
  disbursed_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS loan_customer_idx ON core.loan(customer_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS core.loan_rate_history (
  loan_id TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  effective_from TIMESTAMPTZ NOT NULL,
  annual_rate_percent NUMERIC(5,2) NOT NULL,
  reason TEXT NOT NULL,
  PRIMARY KEY(loan_id, effective_from)
);

CREATE TABLE IF NOT EXISTS core.repayment_schedule_item (
  loan_id TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  installment_no INTEGER NOT NULL CHECK (installment_no > 0),
  due_at TIMESTAMPTZ NOT NULL,
  principal_component NUMERIC(14,2) NOT NULL,
  interest_component NUMERIC(14,2) NOT NULL,
  emi_amount NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('UPCOMING','PAID','MISSED')),
  PRIMARY KEY(loan_id, installment_no)
);

CREATE TABLE IF NOT EXISTS core.failure_code_ref (
  code TEXT PRIMARY KEY,
  customer_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.payment (
  payment_id TEXT PRIMARY KEY CHECK (payment_id ~ '^PM-[0-9]+$'),
  loan_id TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  due_at TIMESTAMPTZ NOT NULL,
  attempted_at TIMESTAMPTZ,
  amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  status TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED','PENDING')),
  failure_code TEXT REFERENCES core.failure_code_ref(code) ON DELETE RESTRICT,
  channel TEXT NOT NULL,
  CHECK ((status = 'FAILED') = (failure_code IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS payment_loan_due_idx ON core.payment(loan_id, due_at DESC);
CREATE INDEX IF NOT EXISTS payment_failed_idx ON core.payment(loan_id, attempted_at DESC) WHERE status = 'FAILED';

CREATE TABLE IF NOT EXISTS core.card_account (
  card_id TEXT PRIMARY KEY CHECK (card_id ~ '^CC-[0-9]+$'),
  customer_id TEXT NOT NULL REFERENCES core.customer(customer_id) ON DELETE RESTRICT,
  product_name TEXT NOT NULL,
  last_four CHAR(4) NOT NULL,
  outstanding NUMERIC(14,2) NOT NULL,
  available_limit NUMERIC(14,2) NOT NULL,
  statement_balance NUMERIC(14,2) NOT NULL,
  due_at TIMESTAMPTZ NOT NULL,
  minimum_due NUMERIC(14,2) NOT NULL,
  reward_points INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS core.card_transaction (
  transaction_id TEXT PRIMARY KEY,
  card_id TEXT NOT NULL REFERENCES core.card_account(card_id) ON DELETE RESTRICT,
  occurred_at TIMESTAMPTZ NOT NULL,
  merchant TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('POSTED','PENDING','REVERSED'))
);

CREATE TABLE IF NOT EXISTS core.policy_rule (
  rule_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  product_code TEXT NOT NULL,
  topic TEXT NOT NULL,
  condition JSONB NOT NULL,
  outcome JSONB NOT NULL,
  clause_id TEXT NOT NULL,
  clause_text TEXT NOT NULL,
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to TIMESTAMPTZ,
  PRIMARY KEY(rule_id, version)
);
CREATE INDEX IF NOT EXISTS policy_lookup_idx ON core.policy_rule(product_code, topic) WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS core.service_request (
  request_id TEXT PRIMARY KEY CHECK (request_id ~ '^SR-[A-Z0-9]+$'),
  customer_id TEXT NOT NULL REFERENCES core.customer(customer_id) ON DELETE RESTRICT,
  loan_id TEXT REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  card_id TEXT REFERENCES core.card_account(card_id) ON DELETE RESTRICT,
  type TEXT NOT NULL,
  subject_ref TEXT,
  summary TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','REJECTED')),
  idempotency_key TEXT NOT NULL UNIQUE,
  request_hash TEXT NOT NULL,
  source_correlation_id UUID NOT NULL,
  expected_resolution_by TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

INSERT INTO core.customer(customer_id,full_name,mobile_e164,kyc_status) VALUES
  ('CU-2291','Aarav Sharma','+919876540721','VERIFIED'),
  ('CU-3140','Mira Iyer','+919876549816','VERIFIED')
ON CONFLICT(customer_id) DO NOTHING;

INSERT INTO core.loan(loan_id,customer_id,product_code,status,sanctioned_amount,outstanding_principal,annual_rate_percent,rate_type,emi_amount,previous_emi,next_due_at,tenure_remaining_months,disbursed_at) VALUES
  ('LN-10045','CU-2291','PERSONAL_LOAN','ACTIVE',500000.00,382450.75,10.75,'FLOATING',11250.00,10950.00,'2026-11-05 00:00:00+05:30',38,'2024-03-05 10:12:00+05:30'),
  ('LN-20418','CU-3140','PERSONAL_LOAN','ACTIVE',350000.00,241180.00,11.20,'FIXED',10230.00,10230.00,'2026-11-10 00:00:00+05:30',29,'2024-07-10 10:12:00+05:30')
ON CONFLICT(loan_id) DO NOTHING;

INSERT INTO core.loan_rate_history(loan_id,effective_from,annual_rate_percent,reason) VALUES
  ('LN-10045','2025-09-01 00:00:00+05:30',10.25,'Floating benchmark rate before September 2026 reset'),
  ('LN-10045','2026-09-01 00:00:00+05:30',10.75,'Floating benchmark rate reset'),
  ('LN-20418','2025-04-01 00:00:00+05:30',11.20,'Fixed rate')
ON CONFLICT(loan_id,effective_from) DO NOTHING;

INSERT INTO core.failure_code_ref(code,customer_text) VALUES
  ('INSUFFICIENT_FUNDS','Not enough balance in the linked account'),
  ('BANK_TIMEOUT','The bank did not respond before the payment timed out'),
  ('MANDATE_INACTIVE','The auto-debit mandate was inactive')
ON CONFLICT(code) DO NOTHING;

INSERT INTO core.payment(payment_id,loan_id,due_at,attempted_at,amount,status,failure_code,channel) VALUES
  ('PM-88213','LN-10045','2026-09-05 00:00:00+05:30','2026-09-05 06:01:12+05:30',11250.00,'FAILED','INSUFFICIENT_FUNDS','AUTO_DEBIT'),
  ('PM-87820','LN-10045','2026-06-05 00:00:00+05:30','2026-06-05 06:00:31+05:30',10950.00,'FAILED','BANK_TIMEOUT','AUTO_DEBIT'),
  ('PM-86109','LN-10045','2026-03-05 00:00:00+05:30','2026-03-05 06:00:43+05:30',10950.00,'FAILED','MANDATE_INACTIVE','AUTO_DEBIT'),
  ('PM-88914','LN-10045','2026-10-05 00:00:00+05:30','2026-10-05 06:00:10+05:30',11250.00,'SUCCESS',NULL,'AUTO_DEBIT'),
  ('PM-91301','LN-20418','2026-08-10 00:00:00+05:30','2026-08-10 05:58:02+05:30',10230.00,'FAILED','INSUFFICIENT_FUNDS','AUTO_DEBIT'),
  ('PM-91752','LN-20418','2026-10-10 00:00:00+05:30','2026-10-10 05:59:11+05:30',10230.00,'SUCCESS',NULL,'AUTO_DEBIT')
ON CONFLICT(payment_id) DO NOTHING;

INSERT INTO core.card_account(card_id,customer_id,product_name,last_four,outstanding,available_limit,statement_balance,due_at,minimum_due,reward_points) VALUES
  ('CC-7042','CU-2291','Horizon Rewards Credit Card','7042',18420.50,81579.50,22340.00,'2026-10-28 00:00:00+05:30',1120.00,3240),
  ('CC-3308','CU-3140','Horizon Platinum Credit Card','3308',9360.00,40640.00,12840.00,'2026-11-02 00:00:00+05:30',650.00,1810)
ON CONFLICT(card_id) DO NOTHING;

INSERT INTO core.card_transaction(transaction_id,card_id,occurred_at,merchant,amount,status) VALUES
  ('TX-50081','CC-7042','2026-10-12 00:00:00+05:30','Green Basket Market',1842.00,'POSTED'),
  ('TX-49823','CC-7042','2026-10-08 00:00:00+05:30','Metroline Travel',4360.00,'POSTED'),
  ('TX-49277','CC-7042','2026-10-02 00:00:00+05:30','CloudNine Media',499.00,'POSTED'),
  ('TX-61003','CC-3308','2026-10-14 00:00:00+05:30','Northwind Books',1290.00,'POSTED'),
  ('TX-60710','CC-3308','2026-10-09 00:00:00+05:30','Urban Outfitters',3280.00,'POSTED')
ON CONFLICT(transaction_id) DO NOTHING;

INSERT INTO core.policy_rule(rule_id,version,product_code,topic,condition,outcome,clause_id,clause_text,effective_from) VALUES
  ('PL-PP-004',1,'PERSONAL_LOAN','PREPAYMENT','{"all":[{"field":"rateType","op":"eq","value":"FLOATING"}]}','{"feePercent":"0.00"}','PL-TERMS-5.4','Part-prepayments are applied to principal. For floating-rate personal loans, no part-prepayment fee applies.','2025-04-01 00:00:00+05:30'),
  ('PL-FC-001',1,'PERSONAL_LOAN','FORECLOSURE','{"all":[{"field":"rateType","op":"eq","value":"FLOATING"}]}','{"penaltyPercent":"0.00"}','PL-TERMS-7.2','No foreclosure charges apply to floating-rate personal loans.','2025-04-01 00:00:00+05:30'),
  ('PAY-OPS-002',1,'PERSONAL_LOAN','PAYMENT_FAILURE','{}','{"disputeAllowed":true}','PAYMENTS-HELP-2.1','Failed debit attempts may be disputed for investigation; the payment remains unpaid until a successful retry is recorded.','2025-04-01 00:00:00+05:30'),
  ('CC-DISPUTE-001',1,'CREDIT_CARD','CARD_DISPUTE','{}','{"disputeAllowed":true}','CARD-TERMS-9.1','Card transactions may be disputed for investigation. A submitted dispute does not guarantee reversal.','2025-04-01 00:00:00+05:30')
ON CONFLICT(rule_id,version) DO NOTHING;
