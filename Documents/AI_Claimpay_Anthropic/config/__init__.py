# config/__init__.py 

# __all__ = ['HybridQuerySystem', 'EnhancedRAGSystem', 'DatabaseManager']

DB_CONFIG = {
    'host': '10.1.0.14',
    'port': 3306,
    'user': 'yeti',
    'password': 'yetidbsecret',
    'database': 'yetiforce'
}


TABLES_CONFIG = {
    'u_yf_claims': [
        'claimsid', 'claim_id', 'provider', 'type_of_claim', 'portfolio',
        'insured', 'createdtime', 'claim_status',
        'total_bill_amount', 'total_collections', 'insurance_company',
        'policy_number', 'date_of_loss', 'date_of_service'
    ],
    'u_yf_cases': [
        'casesid', 'case_id', 'case_number', 'claim_number', 'datecreate',
        'status', 'total_bill_amount', 'total_collections', 'attorney',
        'court', 'insurance_company', 'provider', 'type_of_claim',
        'date_of_service'
    ],
    'u_yf_portfolios': [
        'portfoliosid', 'portfolio_id', 'portfolio_status', 'total_claim_value',
        'total_purchase_price', 'createdtime', 'investor', 'provider',
        'total_collections', 'total_profit'
    ],
    'u_yf_collections': [
        'collectionsid', 'collection_name', 'value', 'collection_type',
        'payment_date', 'insurance_company', 'provider', 'check_number', 'deposit_date'
    ],
    'u_yf_insureds': [
        'insuredsid', 'insured_name', 'number','insured1_first_name', 'insured1_last_name',
        'state','address'
    ],
    'u_yf_claimcollections': [
        'claimcollectionsid', 'claim_collection_name', 'assigned_value',
        'disbursed_date', 'collection', 'portfolio', 'claim', 'portfolio_purchase'
    ],
    'u_yf_outsidecases': [
        'outsidecasesid', 'outside_case_id', 'claim_number', 'total_bill_amount', 'total_collections',  
        'total_balance', 'litigation_status', 'insurance_company', 'provider', 'type_of_claim'
    ],
    'u_yf_portfoliopurchases': [
        'portfoliopurchasesid', 'portfolio_purchase_name', 'purchase_date', 'purchase_value',
        'portfolio_purchase_status', 'total_claim_value', 'portfolio', 'provider', 'funded_date'  
    ],
    'u_yf_providers': [
        'providersid', 'provider_name', 'number', 'is_active', 'type_of_entity',
        'email', 'phone', 'city', 'state'
    ],
    'u_yf_attorneys': [
        'attorneysid', 'attorney_name', 'first_name', 'last_name',
        'attorney_type', 'email', 'phone'
    ],
    'vtiger_modcomments': [
        'modcommentsid', 'commentcontent', 'related_to', 'userid'       
    ],        
    'vtiger_crmentity': [
        'crmid', 'smcreatorid', 'createdtime', 'status', 'deleted'       
    ],
}

    # URL Configurations
URL_CONFIGS = {
    'base_url': 'https://pmcdev.claimpay.net/index.php',
    'modules': {
        'claims': {'module': 'Claims', 'prefix': 'CL_'},
        'portfolios': {'module': 'Portfolios', 'prefix': 'PF_'},
        'cases': {'module': 'Cases', 'prefix': 'CS_'},
        'collections': {'module': 'ClaimCollections', 'prefix': 'COL_'},
        'outside_cases': {'module': 'OutsideCases', 'prefix': 'OC_'}
    }
} 

# Vector Store Settings
VECTOR_STORE_SETTINGS = {
    'chunk_size': 500,
    'chunk_overlap': 50,
    'model_name': "sentence-transformers/all-mpnet-base-v2",
    'device': 'cpu'
}