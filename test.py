-- Savings transactions table
CREATE TABLE IF NOT EXISTS savings_transactions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    savings_account_id UUID NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- Transaction details
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('deposit', 'withdrawal', 'transfer', 'interest', 'fee')),
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'UGX',
    payment_method VARCHAR(20),
    
    -- Reference and description
    reference_number VARCHAR(50) UNIQUE NOT NULL,
    pesapal_order_id VARCHAR(100),
    description TEXT,
    
    -- Account balances
    balance_before DECIMAL(15,2) NOT NULL,
    balance_after DECIMAL(15,2) NOT NULL,
    
    -- Status and processing
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    processed_by UUID REFERENCES admins(id),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Deposit requests table
CREATE TABLE IF NOT EXISTS deposit_requests (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    savings_account_id UUID NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- Deposit details
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'UGX',
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('cash', 'pesapal', 'mobile_money', 'bank_transfer')),
    
    -- Reference and description
    reference_number VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    
    -- PesaPal fields (if applicable)
    pesapal_order_id VARCHAR(100),
    pesapal_reference VARCHAR(100),
    pesapal_status VARCHAR(20),
    pesapal_response JSONB,
    
    -- Status and processing
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    requested_by UUID REFERENCES admins(id),
    confirmed_by UUID REFERENCES admins(id),
    
    -- Timestamps
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Withdrawal requests table
CREATE TABLE IF NOT EXISTS withdrawal_requests (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    savings_account_id UUID NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- Withdrawal details
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'UGX',
    withdrawal_method VARCHAR(20) NOT NULL CHECK (withdrawal_method IN ('cash', 'bank_transfer', 'mobile_money')),
    
    -- Reference and description
    reference_number VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    
    -- Status and processing
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')),
    requested_by UUID REFERENCES admins(id),
    approved_by UUID REFERENCES admins(id),
    rejected_by UUID REFERENCES admins(id),
    rejection_reason TEXT,
    
    -- Timestamps
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejected_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Savings audit log table
CREATE TABLE IF NOT EXISTS savings_audit_log (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    savings_account_id UUID NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    
    -- Audit details
    action VARCHAR(50) NOT NULL,
    description TEXT,
    performed_by UUID REFERENCES admins(id),
    
    -- Client info
    ip_address INET,
    user_agent TEXT,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_savings_transactions_account ON savings_transactions(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_savings_transactions_member ON savings_transactions(member_id);
CREATE INDEX IF NOT EXISTS idx_savings_transactions_date ON savings_transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deposit_requests_account ON deposit_requests(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_deposit_requests_status ON deposit_requests(status);
CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_account ON withdrawal_requests(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_status ON withdrawal_requests(status);