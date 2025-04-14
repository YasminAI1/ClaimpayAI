# app/database.py
import logging
import mysql.connector
import pandas as pd
from typing import Dict, Any, Optional, List, Union

class DatabaseManager:
    """Manages database connections and operations"""
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.connection = None
        logging.info("DatabaseManager initialized with config")
    
    def get_connection(self):
        """Create and return a new database connection"""
        try:
            # Create a new connection each time to avoid timeout issues
            connection = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            return connection
        except Exception as e:
            logging.error(f"Database connection error: {str(e)}")
            raise
    
    def execute_query(self, query: str) -> bool:
        """Execute a query without returning results"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Database error executing query: {str(e)}")
            raise
    
    def fetch_data(self, query: str) -> pd.DataFrame:
        """Execute a query and return results as a DataFrame"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query)
            
            # Fetch all rows as dictionaries
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Convert to DataFrame
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            return df
        except Exception as e:
            logging.error(f"Database error executing query: {str(e)}")
            # Return empty DataFrame on error
            return pd.DataFrame()
    
    def execute_parameterized_query(self, query: str, params: tuple) -> Any:
        """Execute a parameterized query"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            result = cursor.lastrowid
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            logging.error(f"Database error executing parameterized query: {str(e)}")
            raise
    
    def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[tuple]:
        """Fetch a single row from the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            logging.error(f"Database error fetching one row: {str(e)}")
            return None
    
    def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[tuple]:
        """Fetch all rows from the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            logging.error(f"Database error fetching all rows: {str(e)}")
            return []
    
    def fetch_data_with_params(self, query: str, params: tuple) -> pd.DataFrame:
        """Execute a parameterized query and return results as a DataFrame"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            
            # Fetch all rows as dictionaries
            rows = cursor.fetchall()
            
            # Convert to DataFrame
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            return df
        except Exception as e:
            logging.error(f"Database error executing parameterized query: {str(e)}")
            # Return empty DataFrame on error
            return pd.DataFrame()
        finally:
            # Ensure connections are properly closed
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass
    

    def refresh_report_views(self):
        """Refresh materialized views for reporting"""
        try:
            # Re-create the view to ensure fresh data
            refresh_query = """
            CREATE OR REPLACE VIEW vw_claim_reports AS
            SELECT 
                c.claimsid as claim_recordid, 
                c.claim_id, 
                c.claim_number, 
                i.insured_name as insured, 
                p.provider_name as provider, 
                c.date_of_loss, 
                c.total_bill_amount,
                c.claim_status, 
                c.type_of_claim, 
                ce.createdtime as purchased_time,
                pp.purchase_date, 
                pp.funded_date, 
                inv.investor_name as investor,
                pf.portfolio_id
            FROM u_yf_claims c
            JOIN vtiger_crmentity ce ON c.claimsid = ce.crmid
            LEFT JOIN u_yf_insureds i ON c.insured = i.insuredsid
            LEFT JOIN u_yf_providers p ON c.provider = p.providersid
            LEFT JOIN u_yf_portfolio_purchases pp ON c.portfolio_purchase = pp.portfoliopurchasesid
            LEFT JOIN u_yf_portfolios pf ON c.portfolio = pf.portfoliosid
            LEFT JOIN u_yf_investors inv ON pf.investor = inv.investorsid
            WHERE ce.deleted = 0;
            """
            self.execute_query(refresh_query)
            logging.info("Successfully refreshed report views")
            return True
        except Exception as e:
            logging.error(f"Error refreshing report views: {str(e)}")
            return False

    # Add to database.py
    def get_related_comments(self, entity_id: int, entity_type: str = 'Cases') -> pd.DataFrame:
        """Get comments related to an entity from modcomments table"""
        try:
            # First, check if the entity exists
            entity_check_query = """
            SELECT crmid 
            FROM vtiger_crmentity 
            WHERE crmid = %s AND deleted = 0
            """
            entity_check = self.fetch_data_with_params(entity_check_query, (entity_id,))
            
            if entity_check.empty:
                logging.warning(f"No entity found with ID {entity_id}")
                return pd.DataFrame()
            
            # Query for related comments
            comments_query = """
            SELECT 
                mc.modcommentsid,
                mc.commentcontent,
                ce.createdtime,
                ce.smcreatorid,
                u.name as creator_name
            FROM vtiger_modcomments mc
            JOIN vtiger_crmentity ce ON mc.modcommentsid = ce.crmid
            LEFT JOIN users u ON ce.smcreatorid = u.id
            WHERE mc.related_to = %s
            AND ce.deleted = 0
            ORDER BY ce.createdtime DESC
            """
            
            comments_df = self.fetch_data_with_params(comments_query, (entity_id,))
            
            return comments_df
            
        except Exception as e:
            logging.error(f"Error fetching related comments: {str(e)}")
            return pd.DataFrame()
        
    # Add to database.py
    def create_comment_summary_table(self):
        """Create a table to store pre-generated comment summaries"""
        query = """
        CREATE TABLE IF NOT EXISTS comment_summaries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            entity_id INT NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            summary_text TEXT,
            summary_type VARCHAR(20) DEFAULT 'standard',
            comment_count INT DEFAULT 0,
            last_comment_date DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX (entity_id, entity_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self.execute_query(query)
        logging.info("Comment summary table created/verified")

    def store_comment_summary(self, entity_id: int, entity_type: str, summary: str, 
                            summary_type: str, comment_count: int, last_comment_date: str):
        """Store a pre-generated comment summary"""
        query = """
        INSERT INTO comment_summaries 
            (entity_id, entity_type, summary_text, summary_type, comment_count, last_comment_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            summary_text = VALUES(summary_text),
            summary_type = VALUES(summary_type),
            comment_count = VALUES(comment_count),
            last_comment_date = VALUES(last_comment_date),
            updated_at = CURRENT_TIMESTAMP
        """
        params = (entity_id, entity_type, summary, summary_type, comment_count, last_comment_date)
        return self.execute_query_with_params(query, params)

    def get_stored_comment_summary(self, entity_id: int, entity_type: str, summary_type: str = 'standard'):
        """Retrieve a pre-generated comment summary if available"""
        query = """
        SELECT 
            summary_text, comment_count, last_comment_date, updated_at
        FROM comment_summaries
        WHERE entity_id = %s AND entity_type = %s AND summary_type = %s
        """
        params = (entity_id, entity_type, summary_type)
        return self.fetch_data_with_params(query, params)
    
    # Add to database.py

    
    def test_connection(self) -> bool:
        """Test the database connection"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Database connection test failed: {str(e)}")
            raise