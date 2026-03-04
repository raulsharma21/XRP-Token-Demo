-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.fund_state (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  calculation_date date NOT NULL UNIQUE,
  trading_balance_pre_fees numeric NOT NULL,
  total_tokens_outstanding numeric NOT NULL CHECK (total_tokens_outstanding > 0::numeric),
  nav_before_fees numeric NOT NULL,
  fund_hwm_before numeric NOT NULL,
  management_fee_daily_rate numeric NOT NULL DEFAULT 0.00005479,
  management_fee_amount numeric NOT NULL DEFAULT 0,
  performance_fee_rate numeric NOT NULL DEFAULT 0.20,
  performance_fee_amount numeric NOT NULL DEFAULT 0,
  performance_fee_basis numeric,
  total_fees_collected numeric NOT NULL DEFAULT 0,
  trading_balance_post_fees numeric NOT NULL,
  nav_per_token numeric NOT NULL CHECK (nav_per_token > 0::numeric),
  fund_hwm_after numeric NOT NULL,
  hwm_increased boolean NOT NULL DEFAULT false,
  calculated_at timestamp with time zone NOT NULL DEFAULT now(),
  fee_withdrawal_tx_hash text,
  notes text,
  CONSTRAINT fund_state_pkey PRIMARY KEY (id)
);
CREATE TABLE public.investors (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  email character varying NOT NULL UNIQUE,
  xrpl_address character varying NOT NULL UNIQUE,
  kyc_approved boolean DEFAULT false,
  trust_line_created boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT investors_pkey PRIMARY KEY (id)
);
CREATE TABLE public.purchases (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  investor_id uuid,
  usdc_amount numeric,
  token_amount numeric,
  status character varying NOT NULL DEFAULT 'pending'::character varying,
  deposit_tx_hash character varying,
  forward_tx_hash character varying,
  issue_tx_hash character varying,
  destination_tag bigint,
  created_at timestamp with time zone DEFAULT now(),
  completed_at timestamp with time zone,
  CONSTRAINT purchases_pkey PRIMARY KEY (id),
  CONSTRAINT purchases_investor_id_fkey FOREIGN KEY (investor_id) REFERENCES public.investors(id)
);
CREATE TABLE public.redemptions (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  investor_id uuid,
  token_amount numeric NOT NULL,
  nav_price numeric,
  usdc_amount numeric,
  status character varying NOT NULL DEFAULT 'queued'::character varying,
  redemption_tx_hash character varying,
  requested_at timestamp with time zone DEFAULT now(),
  settled_at timestamp with time zone,
  destination_tag bigint,
  burn_tx_hash text,
  detected_at timestamp with time zone,
  CONSTRAINT redemptions_pkey PRIMARY KEY (id),
  CONSTRAINT redemptions_investor_id_fkey FOREIGN KEY (investor_id) REFERENCES public.investors(id)
);
CREATE TABLE public.system_config (
  key character varying NOT NULL,
  value text NOT NULL,
  description text,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT system_config_pkey PRIMARY KEY (key)
);
CREATE TABLE public.transactions_log (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  tx_hash character varying NOT NULL UNIQUE,
  tx_type character varying NOT NULL,
  from_address character varying,
  to_address character varying,
  amount numeric,
  currency character varying,
  related_purchase_id uuid,
  related_redemption_id uuid,
  metadata jsonb,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT transactions_log_pkey PRIMARY KEY (id),
  CONSTRAINT transactions_log_related_purchase_id_fkey FOREIGN KEY (related_purchase_id) REFERENCES public.purchases(id),
  CONSTRAINT transactions_log_related_redemption_id_fkey FOREIGN KEY (related_redemption_id) REFERENCES public.redemptions(id)
);