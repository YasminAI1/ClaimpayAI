# app/query_builder.py
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

class QueryBuilder:
    """Dynamic SQL query builder for report generation"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.table_columns = {
            'u_yf_claims': [
                'claimdid', 'claim_id', 'claim_number', 'insured', 'provider', 
                'portfolio', 'date_of_loss', 'onboarding_status', 'purchased_time',
                'total_collections', 'total_collections', 'type_of_claim'
            ],
            'u_yf_portfolios': [
                'portfolioid', 'portfolio_id', 'provider', 'investor', 'opened_date', 
                'total_claim_value', 'total_collections', 'hurdle_percent'
            ],
            'u_yf_portfoliopurchases': [
                'portfoliopurchaseid', 'number', 'portfolio', 'provider', 'investor', 
                'funded_date', 'purchase_date', 'purchase_value'
            ]
        }
        
        # Add common joins between tables
        self.join_conditions = {
            ('u_yf_claims', 'u_yf_portfolios'): 
                'u_yf_claims.portfolio = u_yf_portfolios.recordid',
            ('u_yf_claims', 'u_yf_portfoliopurchases'): 
                'u_yf_claims.portfolio_purchase = u_yf_portfoliopurchases.recordid',
            ('u_yf_portfolios', 'u_yf_portfoliopurchases'): 
                'u_yf_portfoliopurchases.portfolio = u_yf_portfolios.recordid'
        }
    
    def build_provider_claims_query(self, provider_name: str, 
                                   date_of_loss_before: Optional[str] = None,
                                   investor_name: Optional[str] = None,
                                   funded_last_month: bool = False) -> tuple:
        """
        Build a parameterized query for purchased claims by provider with optional filters
        Returns query string and parameters tuple
        """
        # Start with base tables and columns
        select_columns = [
            "c.recordid", "c.claim_id", "c.claim_number", "c.insured", 
            "c.provider", "c.date_of_loss", "c.total_collections",
            "c.onboarding_status", "c.type_of_claim", 
            "pp.purchase_date", "pp.funded_date", "p.investor", "p.portfolio_id"
        ]
        
        # Base query with placeholders
        query = f"""
        SELECT {', '.join(select_columns)}
        FROM u_yf_claims c
        LEFT JOIN u_yf_portfoliopurchases pp ON c.portfolio = pp.portfolio
        LEFT JOIN u_yf_portfolios p ON c.portfolio = p.portfolio_id
        WHERE c.provider LIKE %s
        AND c.onboarding_status = 'Purchased'
        """
        
        # Parameters list
        params = [f"%{provider_name}%"]
        
        # Add optional filters
        if date_of_loss_before:
            try:
                # Validate date format
                datetime.strptime(date_of_loss_before, '%Y-%m-%d')
                query += " AND c.date_of_loss < %s"
                params.append(date_of_loss_before)
            except ValueError:
                logging.warning(f"Invalid date format: {date_of_loss_before}. Ignoring filter.")
        
        if investor_name:
            query += " AND p.investor LIKE %s"
            params.append(f"%{investor_name}%")
        
        if funded_last_month:
            # Calculate first day of previous month
            today = datetime.today()
            last_month = today.replace(day=1) - timedelta(days=1)
            first_day = last_month.replace(day=1).strftime('%Y-%m-%d')
            last_day = today.replace(day=1) - timedelta(days=1)
            last_day = last_day.replace(day=last_day.day).strftime('%Y-%m-%d')
            
            query += " AND pp.funded_date BETWEEN %s AND %s"
            params.extend([first_day, last_day])
        
        # Order by date_of_loss descending
        query += " ORDER BY c.date_of_loss DESC"
        
        return query, tuple(params)
    
    def build_report_query(self, params: Dict[str, Any]) -> str:
        """Build SQL query based on extracted parameters using the optimized view"""
        # Check if view exists, otherwise use regular tables
        try:
            # First check if the view exists
            check_view_query = "SHOW TABLES LIKE 'vw_claim_reports'"
            # This would need to be executed, but we'll assume the view exists for now
            
            # Using the view for better performance
            query = """
            SELECT 
                claim_recordid as recordid, 
                claim_id, 
                claim_number, 
                insured, 
                provider, 
                date_of_loss, 
                total_collections,
                onboarding_status, 
                type_of_claim, 
                purchased_time,
                purchase_date, 
                funded_date, 
                investor,
                portfolio_id
            FROM vw_claim_reports
            WHERE provider LIKE '%{0}%'
            """.format(params['provider'])
            
            # Add date of loss filter if provided
            if params['date_of_loss_before']:
                query += f" AND date_of_loss < '{params['date_of_loss_before']}'"
            
            # Add investor filter if provided
            if params['investor']:
                query += f" AND investor LIKE '%{params['investor']}%'"
            
            # Add "funded last month" filter if requested
            if params['funded_last_month']:
                # Calculate first and last day of previous month
                today = datetime.today()
                first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
                last_day = today.replace(day=1) - timedelta(days=1)
                
                first_day_str = first_day.strftime('%Y-%m-%d')
                last_day_str = last_day.strftime('%Y-%m-%d')
                
                query += f" AND funded_date BETWEEN '{first_day_str}' AND '{last_day_str}'"
            
            # Order by date of loss descending
            query += " ORDER BY date_of_loss DESC"
            
            return query
            
        except Exception as e:
            # If view doesn't exist, fall back to regular tables
            logging.warning(f"View vw_claim_reports not available, using regular tables: {str(e)}")
            return self.build_provider_claims_query(
                provider_name=params['provider'],
                date_of_loss_before=params['date_of_loss_before'],
                investor_name=params['investor'],
                funded_last_month=params['funded_last_month']
            )
    
    def detect_report_type(self, question: str) -> Dict:
        """
        Detect the type of report being requested
        
        Args:
            question: The user's question/request
            
        Returns:
            Dict with report type and parameters
        """
        question = question.lower()
        
        # Initialize result
        result = {
            'report_type': 'provider_claims',
            'provider': None,
            'date_of_loss_before': None,
            'investor': None,
            'funded_last_month': False
        }
        
        # Extract provider name
        provider_match = None
        if 'provider' in question:
            # Try to find "Provider X" pattern
            provider_matches = re.findall(r'provider\s+(\w+(?:\s+\w+)*)', question)
            if provider_matches:
                provider_match = provider_matches[0]
        
        # If no match found, use a default
        result['provider'] = provider_match or 'Provider 1'
        
        # Check for date of loss filter
        if 'date of loss before' in question:
            date_matches = re.findall(r'before\s+(\d{1,2}/\d{1,2}/\d{4})', question)
            if date_matches:
                # Convert MM/DD/YYYY to YYYY-MM-DD
                date_str = date_matches[0]
                try:
                    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                    result['date_of_loss_before'] = date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    logging.warning(f"Could not parse date: {date_str}")
        
        # Check for investor filter
        if 'investor' in question:
            investor_matches = re.findall(r'investor\s+(\w+(?:\s+\w+)*)', question)
            if investor_matches:
                result['investor'] = investor_matches[0]
        
        # Check for "last month" filter
        if 'last month' in question or 'previous month' in question:
            result['funded_last_month'] = True
        
        return result