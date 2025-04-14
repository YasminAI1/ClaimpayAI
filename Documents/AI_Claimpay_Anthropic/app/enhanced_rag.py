# In enhanced_rag.py
from .comment_summarizer import CommentSummarizer
from typing import List, Dict, Any, Optional, Union
import pandas as pd
import logging
import re
from datetime import datetime
import os  # Add this import
from .database import DatabaseManager
from .vector_store import EnhancedVectorStore
from .url_generator import URLGenerator
from .encryption import DataEncryption
from time import sleep
from functools import wraps
import random
# In app/enhanced_rag.py or a new file:
from .schema_inspector import SchemaInspector
from .report_builder import ReportBuilder
from .excel_converter import AnswerToExcel
from .report_engine import ReportEngine
from .excel_converter import ReportQueryBuilder
# Import the QueryBuilder class if not already imported
from .query_builder import QueryBuilder
# from .materialized_views import MaterializedViewManager

class RateLimiter:
    def __init__(self, max_retries=3, base_delay=1):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if 'overloaded' in str(e).lower():
                        delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logging.info(f"Rate limit reached. Retrying in {delay:.2f} seconds...")
                        sleep(delay)
                    else:
                        raise e
                        
            logging.error(f"Max retries reached. Last error: {last_exception}")
            return {
                "answer": "The system is currently experiencing high load. Please try again in a few moments.",
                "recordid": None,
                "link": None
            }
            
        return wrapper

class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.last_failure_time = None
        self.is_open = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True

    def can_execute(self):
        if not self.is_open:
            return True
            
        if self.last_failure_time and \
           (datetime.now() - self.last_failure_time).seconds >= self.reset_timeout:
            self.reset()
            return True
            
        return False

    def reset(self):
        self.failure_count = 0
        self.last_failure_time = None
        self.is_open = False


class EnhancedRAGSystem:
    def __init__(self, db_config: dict):
        self.db_manager = DatabaseManager(db_config)
        self.table_vectors = {} 
        self.encryption = DataEncryption()
        self.url_generator = URLGenerator()
        self.rate_limiter = RateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self.excel_converter= AnswerToExcel()
        self.report_engine = ReportEngine(self.db_manager)
        self.comment_summarizer = CommentSummarizer(self.db_manager)
            # Initialize schema inspector
        self.schema_inspector = SchemaInspector(self.db_manager)
        
        # Initialize report builder with schema inspector
        self.report_builder = ReportBuilder(self.db_manager, self.schema_inspector)
        
        # Make sure this exists in your __init__ method
        self.datetime_columns = {
            'u_yf_cases': None,
            'u_yf_claims': 'createdtime',
            'u_yf_portfolios': 'createdtime',
            'u_yf_collections': 'createdtime',
            'u_yf_insureds': 'createdtime',
            'u_yf_claimcollections': 'createdtime',
            'u_yf_outside_cases': 'createdtime',
            'u_yf_portfoliopurchases': 'createdtime'
        }

    def _is_report_request(self, question: str) -> bool:
        """Determine if the question is asking for a report"""
        report_keywords = [
            'report', 'excel', 'export', 'list all', 'show me all',
            'all purchased claims', 'generate a report'
        ]
        return any(keyword in question.lower() for keyword in report_keywords)


    def _get_datetime_column(self, table_name: str) -> str:
        """Get the appropriate datetime column name for each table"""
        return self.datetime_columns.get(table_name, 'createdtime')

    def initialize_table(self, table_name: str, columns: List[str]):
        """Initialize a table with vector store"""
        try:
            # Build and execute query
            query = self._build_table_query(table_name, columns)
            df = self.db_manager.fetch_data(query)
            
            if df.empty:
                logging.warning(f"No data found for table {table_name}")
                return
            
            # Create vector store
            vector_store = EnhancedVectorStore(self.encryption)
            documents = self._prepare_documents(df, table_name)
            vector_store.create_vector_store(documents, table_name)
            
            # Store references
            self.table_vectors[table_name] = {
                'store': vector_store,
                'df': df
            }
            
            logging.info(f"Successfully initialized table: {table_name}")
            
        except Exception as e:
            logging.error(f"Error initializing table {table_name}: {str(e)}")
            logging.error(f"Database error: {str(e)}")
            raise

    def _build_table_query(self, table_name: str, columns: List[str]) -> str:
        """Build SQL query for table initialization"""
        # Ensure 'recordid' is in columns
        if 'recordid' not in columns:
            columns.append('recordid')

        # Format columns with backticks
        formatted_columns = [f"`{col}`" if col != 'case' else '`case`' for col in columns]

        # Get datetime column
        datetime_col = self._get_datetime_column(table_name)

        # Add formatted time
        if datetime_col:
            # Add formatted time if datetime column exists
            query = f"""
            SELECT DISTINCT
                {', '.join(formatted_columns)},
                DATE_FORMAT(`{datetime_col}`, '%Y-%m-%d %H:%i') as formatted_time
            FROM {table_name}
            WHERE `{datetime_col}` IS NOT NULL
            ORDER BY `{datetime_col}` DESC
            LIMIT 1000
            """
        else:   
            # Query without datetime handling for tables like u_yf_cases
            query = f"""
            SELECT DISTINCT
                {', '.join(formatted_columns)}
            FROM {table_name}
            LIMIT 1000
            """
        return query
    

    
    def _map_datetime_column(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Map datetime columns to consistent names across tables"""
        datetime_col = self._get_datetime_column(table_name)
        if datetime_col != 'createdtime' and datetime_col in df.columns:
            df['createdtime'] = df[datetime_col]
        
        elif not datetime_col:
            # For tables without datetime columns, add a placeholder
            df['createdtime'] = 'Not Available'
            df['formatted_time'] = 'Not Available'

        return df        
        

    def _prepare_documents(self, df: pd.DataFrame, table_name: str) -> List[str]:
        """Prepare documents for vector store"""
        documents = []
        for _, row in df.iterrows():
            doc = self._format_record_text(row, table_name)
            if doc:  # Only add non-empty documents
                documents.append(doc)
        return documents

    def _format_record_text(self, row: pd.Series, table_name: str) -> str:
        """Format record into searchable text"""
        try:
            # Basic record information
            text_parts = [f"Record ID: {row.get('recordid', 'N/A')}"]
            
            # Add creation time if available
            if 'formatted_time' in row and row['formatted_time'] != 'Not Available':
                text_parts.append(f"Created: {row.get('formatted_time', 'N/A')}")
            
            # Add all non-null values from the row
            for column, value in row.items():
                if pd.notna(value) and column not in ['recordid', 'formatted_time', 'createdtime']:
                    text_parts.append(f"{column}: {value}")
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logging.error(f"Error formatting record text: {str(e)}")
            return ""
        
    def _map_datetime_column(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Map datetime columns to consistent names across tables"""
        datetime_col = self._get_datetime_column(table_name)
        if datetime_col != 'createdtime' and datetime_col in df.columns:
            df['createdtime'] = df[datetime_col]
        return df

    def _determine_table_relevance(self, question: str) -> dict:
        """Determine which table is most relevant to the question"""
        question_lower = question.lower()
        patterns = {
            'claims': (['claim', 'insurance'], 'u_yf_claims'),
            'portfolios': (['portfolio', 'investment'], 'u_yf_portfolios'),
            'cases': (['case', 'legal'], 'u_yf_cases'),
            'collections': (['collection', 'payment'], 'u_yf_collections'),
            'outside_cases': (['outside case'], 'u_yf_outside_cases')
        }
            
        for record_type, (keywords, table_name) in patterns.items():
            if any(keyword in question_lower for keyword in keywords):
                return {
                    'record_type': record_type,
                    'table_name': table_name
                }
        
        return {
            'record_type': 'claims',
            'table_name': 'u_yf_claims'
        }

    def _extract_record_info(self, content: str, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Extract record information from content"""
        try:
            id_match = re.search(r'(Claim|Portfolio|Case) ID: ([^\n]+)', content)
            if not id_match:
                return None
                
            id_value = id_match.group(2).strip()
            id_column = self._get_id_column(df.columns)
                
            if not id_column:
                return None
                
            matching_row = df[df[id_column] == id_value]
                
            if matching_row.empty:
                return None
                
            return {
                'recordid': int(matching_row.iloc[0]['recordid']),
                'id': id_value
            }
                
        except Exception as e:
            logging.error(f"Error extracting record info: {str(e)}")
            return None

    def _get_id_column(self, columns: pd.Index) -> Optional[str]:
        """Get the appropriate ID column name"""
        id_columns = {
            'recordid':'recordid',
            'claim_id': 'claims',
            'portfolio_id': 'portfolios',
            'case_id': 'cases'
        }
            
        for col in columns:
            if col in id_columns:
                return col
        return None

    def _format_answer(self, content: str) -> str:
        """Format the answer for output"""
        lines = content.split('\n')
        formatted_lines = []
        for line in lines:
            if not line.startswith(('Internal:', 'Technical:', 'Debug:')):
                formatted_lines.append(line)
        return "\n".join(formatted_lines)

    def _format_response(self, data: Dict[str, Any], response_type: str = 'claim') -> dict:
        """Format response data into a standardized structure"""
        try:
            if response_type == 'claim':
                formatted_answer = (
                    f"The {data.get('query_type', '')} claim in the system is:\n"
                    f"- Claim ID: {data.get('claim_id', 'N/A')}\n"
                    f"- Claim Number: {data.get('claim_number', 'N/A')}\n"
                    f"- Insured: {data.get('insured', 'N/A')}\n"
                    f"- Provider: {data.get('provider', 'N/A')}\n"
                    f"- Date of Loss: {data.get('date_of_loss', 'N/A')}\n"
                    f"- Type of Claim: {data.get('type_of_claim', 'N/A')}\n"
                    f"- Status: {data.get('claim_status', 'N/A')}\n"
                    f"- Total Bill Amount: ${data.get('total_collections', 0):,.2f}"
                )
                
                if data.get('createdtime'):
                    formatted_answer += f"\n- Created on: {data['createdtime']}"
                    
                return {
                    "answer": formatted_answer,
                    "recordid": data.get('recordid'),
                    "link": self.url_generator.generate_url('claims', data.get('recordid')) if data.get('recordid') else None
                }
                
            return {
                "answer": "Unsupported response type",
                "recordid": None,
                "link": None
            }
            
        except Exception as e:
            logging.error(f"Error formatting response: {str(e)}")
            return {
                "answer": "Error formatting the response",
                "recordid": None,
                "link": None
            }

    def _should_export_excel(self, question: str) -> bool:
        """Check if the query requests Excel export"""
        excel_keywords = ['excel', 'export', 'download', 'spreadsheet']
        return any(keyword in question.lower() for keyword in excel_keywords)
        
    # Modify enhanced_rag.py to add this method

    def _is_report_request(self, question: str) -> bool:
        """Determine if the question is asking for a report"""
        question_lower = question.lower()
        
        report_keywords = [
            'report', 'excel', 'export', 'list all', 'show me all', 'show all',
            'all purchased claims', 'generate a report', 'claims of', 
            'claims from', 'claims by', 'all claims'
        ]
        
        specific_provider_indicators = [
            'total care restoration', 'tcr', 'usa restoration', 
            'aqa', '24/7 restoration', 'disaster solutions'
        ]
        
        # Check for report keywords
        keyword_match = any(keyword in question_lower for keyword in report_keywords)
        
        # Check for specific provider mentions
        provider_match = any(provider in question_lower for provider in specific_provider_indicators)
        
        # If both a report keyword and provider name are found, it's definitely a report request
        if keyword_match and provider_match:
            logging.info(f"Identified as report request with provider mention: {question}")
            return True
        
        # If just report keywords are found
        if keyword_match:
            logging.info(f"Identified as report request by keywords: {question}")
            return True
        
        # Not a report request
        return False

        # Update the query method

    # Add this new method to detect comment summary requests
# Add this method to your EnhancedRAGSystem class
    def _is_comment_summary_request(self, question: str) -> bool:
        """Determine if the question is asking for a comment summary"""
        comment_keywords = [
            'comment summary', 'summarize comments', 'comment highlights',
            'what do the comments say', 'summary of comments', 'case comments',
            'show me the comments', 'extract from comments', 'comment extraction',
            'case summary', 'summary of case', 'summarize case', 'case details', 'show me case'
        ]
        
        question_lower = question.lower()
        
        # Check for comment keywords
        has_comment_keyword = any(keyword in question_lower for keyword in comment_keywords)
        
        # Check for case identifiers using a broader pattern to catch more formats
        case_pattern = r'(case|CS|PDC)\s*[-:]?\s*(\w+[-]?\d+)'
        has_case_identifier = re.search(case_pattern, question, re.IGNORECASE) is not None
        
        return has_comment_keyword or has_case_identifier
    
    
    # Modify the query method in your EnhancedRAGSystem class:

    @RateLimiter()
    def query(self, question: str) -> Union[dict, List[dict]]:
        try:
            # First, check if database connection is working
            try:
                self.db_manager.test_connection()
            except Exception as db_error:
                logging.error(f"Database connection error: {str(db_error)}")
                return {
                    "answer": "Unable to connect to the database. Please try again later or contact support.",
                    "recordid": None,
                    "link": None
                }
            
            # Check if this is a report request
            if self._is_report_request(question):
                logging.info(f"Processing report request: {question}")
                
                # Generate report using the new ReportBuilder
                return self.report_builder.generate_report(question)
                
            # Check if this is a case/comment summary request
            elif self._is_comment_summary_request(question):
                logging.info(f"Processing case summary request: {question}")
                return self._handle_case_summary_query(question)
            
            # Handle specific claim queries
            elif any(pattern in question.lower() for pattern in ["first claim", "earliest claim", "oldest claim"]):
                try:
                    result = self._handle_first_claim_query()
                    # Ensure we always return a dictionary
                    return result if result is not None else {
                        "answer": "I couldn't retrieve information about the first claim.",
                        "recordid": None,
                        "link": None
                    }
                except Exception as e:
                    logging.error(f"Error handling first claim query: {str(e)}", exc_info=True)
                    return {
                        "answer": "I couldn't retrieve the first claim due to a technical issue.",
                        "recordid": None,
                        "link": None
                    }
                    
            elif any(pattern in question.lower() for pattern in ["last claim", "latest claim", "most recent", "newest"]):
                try:
                    result = self._handle_last_claim_query()
                    # Ensure we always return a dictionary
                    return result if result is not None else {
                        "answer": "I couldn't retrieve information about the latest claim.",
                        "recordid": None,
                        "link": None
                    }
                except Exception as e:
                    logging.error(f"Error handling last claim query: {str(e)}", exc_info=True)
                    return {
                        "answer": "I couldn't retrieve the latest claim due to a technical issue.",
                        "recordid": None,
                        "link": None
                    }
            
            # Default to vector query for other types of questions
            else:
                try:
                    result = self._handle_vector_query(question)
                    # Ensure we always return a dictionary
                    return result if result is not None else {
                        "answer": "I don't have enough information to answer that question.",
                        "recordid": None,
                        "link": None
                    }
                except Exception as vector_error:
                    logging.error(f"Vector query error: {str(vector_error)}", exc_info=True)
                    return {
                        "answer": "I wasn't able to find relevant information for your query.",
                        "recordid": None,
                        "link": None
                    }

        except Exception as e:
            logging.error(f"Query error: {str(e)}", exc_info=True)
            # Return a fallback response
            return {
                "answer": "An error occurred processing your request. Please try a different question.",
                "recordid": None,
                "link": None
            }
            
    def _execute_query(self, question: str) -> dict:
        """Execute the actual query based on the question type"""
        # Determine query type
        if any(pattern in question.lower() for pattern in ["first claim", "earliest claim", "oldest claim"]):
            return self._handle_first_claim_query()
            
        elif any(pattern in question.lower() for pattern in ["last claim", "latest claim", "most recent", "newest"]):
            return self._handle_last_claim_query()
            
        else:
            return self._handle_vector_query(question)

    def _handle_first_claim_query(self) -> dict:
        """Handle queries for the first claim with error handling"""
        try:
            # Use the schema inspector to get the correct column names
            claims_table = "u_yf_claims"
            primary_key = self.schema_inspector.get_primary_key(claims_table)
            
            # Build a query using only columns that exist
            available_columns = self.schema_inspector.get_table_columns(claims_table)
            
            select_parts = [f"c.{primary_key} AS recordid"]
            
            # Add basic columns if they exist
            for col in ['claim_id', 'claim_number', 'date_of_loss', 'claim_status']:
                if col in available_columns:
                    select_parts.append(f"c.{col}")
            
            # Always include createdtime from entity table
            select_parts.append("e.createdtime")
            
            # Handle provider and insured (could be IDs or related tables)
            if 'provider' in available_columns:
                # Check if provider table exists for lookup
                if "u_yf_providers" in self.schema_inspector.schema_cache:
                    provider_id_col = self.schema_inspector.get_primary_key("u_yf_providers")
                    provider_name_col = self.schema_inspector.get_name_column("u_yf_providers")
                    if provider_name_col:
                        select_parts.append(f"IFNULL(p.{provider_name_col}, c.provider) AS provider")
                        join_provider = True
                    else:
                        select_parts.append("c.provider")
                        join_provider = False
                else:
                    select_parts.append("c.provider")
                    join_provider = False
            else:
                join_provider = False
            
            if 'insured' in available_columns:
                # Check if insured table exists for lookup
                if "u_yf_insureds" in self.schema_inspector.schema_cache:
                    insured_id_col = self.schema_inspector.get_primary_key("u_yf_insureds")
                    insured_name_col = self.schema_inspector.get_name_column("u_yf_insureds")
                    if insured_name_col:
                        select_parts.append(f"IFNULL(i.{insured_name_col}, c.insured) AS insured")
                        join_insured = True
                    else:
                        select_parts.append("c.insured")
                        join_insured = False
                else:
                    select_parts.append("c.insured")
                    join_insured = False
            else:
                join_insured = False
            
            # Build the joins part of the query
            joins = ["JOIN vtiger_crmentity e ON c.claimsid = e.crmid"]
            
            if join_provider:
                joins.append(f"LEFT JOIN u_yf_providers p ON c.provider = p.{provider_id_col}")
                
            if join_insured:
                joins.append(f"LEFT JOIN u_yf_insureds i ON c.insured = i.{insured_id_col}")
            
            # Build the final query
            query = f"""
            SELECT {', '.join(select_parts)}
            FROM {claims_table} c
            {' '.join(joins)}
            WHERE e.deleted = 0
            ORDER BY e.createdtime ASC 
            LIMIT 1
            """
            
            logging.info(f"Executing first claim query: {query}")
            
            df = self.db_manager.fetch_data(query)
            
            if df.empty:
                return {
                    "answer": "No claims found in the system",
                    "recordid": None,
                    "link": None
                }
            
            result = df.iloc[0]
            
            # Build formatted answer dynamically based on available columns
            answer_parts = ["The first claim in the system is:"]
            
            for col in df.columns:
                if col != 'recordid' and pd.notna(result[col]):
                    # Format the column name for display
                    display_name = col.replace('_', ' ').title()
                    value = result[col]
                    
                    # Format dates
                    if isinstance(value, pd.Timestamp):
                        value = value.strftime('%Y-%m-%d')
                    
                    answer_parts.append(f"- {display_name}: {value}")
            
            formatted_answer = "\n".join(answer_parts)
            
            recordid = int(result['recordid'])
            url = self.url_generator.generate_url('claims', recordid)
            
            return {
                "answer": formatted_answer,
                "recordid": recordid,
                "link": url
            }
            
        except Exception as e:
            logging.error(f"Error in _handle_first_claim_query: {str(e)}", exc_info=True)
            return {
                "answer": f"Error retrieving the first claim: {str(e)}",
                "recordid": None,
                "link": None
            }

    def _handle_vector_query(self, question: str) -> Union[dict, List[dict]]:
        """Handle vector-based queries with support for multiple results"""
        try:
            # Check if it's a request for last 10 claims
            if "last ten claims" in question.lower() or "last 10 claims" in question.lower():
                query = """
                SELECT claim_id, provider, date_of_loss 
                FROM u_yf_claims 
                ORDER BY date_of_loss DESC 
                LIMIT 10
                """
                df = self.db_manager.fetch_data(query)
                
                if not df.empty:
                    results = [tuple(x) for x in df.to_numpy()]
                    return results
            
            # Regular vector query handling
            table_relevance = self._determine_table_relevance(question)
            table_data = self.table_vectors.get(table_relevance['table_name'])
            
            if not table_data:
                return {
                    "answer": "No relevant data found for your question",
                    "recordid": None,
                    "link": None
                }
            
            results = table_data['store'].query(question, k=5)
            
            if not results:
                return {
                    "answer": "No matching information found",
                    "recordid": None,
                    "link": None
                }
            
            formatted_results = [
                self._format_response(result, table_relevance['record_type'])
                for result in results
            ]
            
            return formatted_results[0] if len(formatted_results) == 1 else formatted_results
            
        except Exception as e:
            logging.error(f"Error in vector query: {str(e)}")
            raise

    def _handle_last_claim_query(self) -> dict:
        """Handle queries for the most recent claim"""
        try:
            # Use the schema inspector to get the correct column names
            claims_table = "u_yf_claims"
            primary_key = self.schema_inspector.get_primary_key(claims_table)
            
            # Build a query using only columns that exist
            available_columns = self.schema_inspector.get_table_columns(claims_table)
            
            select_parts = [f"c.{primary_key} AS recordid"]
            
            # Add basic columns if they exist
            for col in ['claim_id', 'claim_number', 'date_of_loss', 'claim_status']:
                if col in available_columns:
                    select_parts.append(f"c.{col}")
            
            # Always include createdtime from entity table
            select_parts.append("e.createdtime")
            
            # Handle provider and insured (could be IDs or related tables)
            if 'provider' in available_columns:
                # Check if provider table exists for lookup
                if "u_yf_providers" in self.schema_inspector.schema_cache:
                    provider_id_col = self.schema_inspector.get_primary_key("u_yf_providers")
                    provider_name_col = self.schema_inspector.get_name_column("u_yf_providers")
                    if provider_name_col:
                        select_parts.append(f"IFNULL(p.{provider_name_col}, c.provider) AS provider")
                        join_provider = True
                    else:
                        select_parts.append("c.provider")
                        join_provider = False
                else:
                    select_parts.append("c.provider")
                    join_provider = False
            else:
                join_provider = False
            
            if 'insured' in available_columns:
                # Check if insured table exists for lookup
                if "u_yf_insureds" in self.schema_inspector.schema_cache:
                    insured_id_col = self.schema_inspector.get_primary_key("u_yf_insureds")
                    insured_name_col = self.schema_inspector.get_name_column("u_yf_insureds")
                    if insured_name_col:
                        select_parts.append(f"IFNULL(i.{insured_name_col}, c.insured) AS insured")
                        join_insured = True
                    else:
                        select_parts.append("c.insured")
                        join_insured = False
                else:
                    select_parts.append("c.insured")
                    join_insured = False
            else:
                join_insured = False
            
            # Build the joins part of the query
            joins = ["JOIN vtiger_crmentity e ON c.claimsid = e.crmid"]
            
            if join_provider:
                joins.append(f"LEFT JOIN u_yf_providers p ON c.provider = p.{provider_id_col}")
                
            if join_insured:
                joins.append(f"LEFT JOIN u_yf_insureds i ON c.insured = i.{insured_id_col}")
            
            # Build the final query
            query = f"""
            SELECT {', '.join(select_parts)}
            FROM {claims_table} c
            {' '.join(joins)}
            WHERE e.deleted = 0
            ORDER BY e.createdtime DESC 
            LIMIT 1
            """
            
            logging.info(f"Executing last claim query: {query}")
            
            df = self.db_manager.fetch_data(query)
            
            if df.empty:
                return {
                    "answer": "No claims found in the system",
                    "recordid": None,
                    "link": None
                }
            
            result = df.iloc[0]
            
            # Build formatted answer dynamically based on available columns
            answer_parts = ["The most recent claim in the system is:"]
            
            for col in df.columns:
                if col != 'recordid' and pd.notna(result[col]):
                    # Format the column name for display
                    display_name = col.replace('_', ' ').title()
                    value = result[col]
                    
                    # Format dates
                    if isinstance(value, pd.Timestamp):
                        value = value.strftime('%Y-%m-%d')
                    
                    answer_parts.append(f"- {display_name}: {value}")
            
            formatted_answer = "\n".join(answer_parts)
            
            recordid = int(result['recordid'])
            url = self.url_generator.generate_url('claims', recordid)
            
            return {
                "answer": formatted_answer,
                "recordid": recordid,
                "link": url
            }
            
        except Exception as e:
            logging.error(f"Error in _handle_last_claim_query: {str(e)}", exc_info=True)
            return {
                "answer": f"Error retrieving the most recent claim: {str(e)}",
                "recordid": None,
                "link": None
            }
        
    def _handle_case_summary_query(self, question: str) -> dict:
        """Handle queries requesting case or comment summaries"""
        try:
            # Extract case number or ID
            case_pattern = r'(case|CS|PDC)\s*[-:]?\s*(\w+[-]?\d+)'
            case_match = re.search(case_pattern, question, re.IGNORECASE)
            
            if not case_match:
                return {
                    "answer": "I couldn't identify a case number in your request. Please specify a case number like 'PDC22-109768'.",
                    "recordid": None,
                    "link": None
                }
            
            case_id = case_match.group(2)
            logging.info(f"Looking for case with identifier: {case_id}")
            
            # Query to get case details
            query = """
            SELECT 
                c.casesid AS recordid,
                c.case_id,
                c.case_number,
                c.claim_number,
                p.provider_name AS provider,
                i.insured_name AS insured,
                c.date_of_loss,
                c.status,
                e.createdtime
            FROM u_yf_cases cgit 
            JOIN vtiger_crmentity e ON c.casesid = e.crmid
            LEFT JOIN u_yf_providers p ON c.provider = p.providersid
            LEFT JOIN u_yf_insureds i ON c.insured = i.insuredsid
            WHERE (c.case_number = %s OR c.case_id = %s)
            AND e.deleted = 0
            LIMIT 1
            """
            
            df = self.db_manager.fetch_data_with_params(query, (case_id, case_id))
            
            if df.empty:
                return {
                    "answer": f"No case found with identifier: {case_id}",
                    "recordid": None,
                    "link": None
                }
            
            case = df.iloc[0]
            
            # Query for case comments
            comments_query = """
            SELECT 
                mc.commentcontent,
                u.name AS creator_name,
                e.createdtime
            FROM vtiger_modcomments mc
            JOIN vtiger_crmentity e ON mc.modcommentsid = e.crmid
            LEFT JOIN users u ON e.smcreatorid = u.id
            WHERE mc.related_to = %s
            AND e.deleted = 0
            ORDER BY e.createdtime DESC
            LIMIT 10
            """
            
            comments_df = self.db_manager.fetch_data_with_params(comments_query, (case['recordid'],))
            
            # Create case summary
            formatted_answer = (
                f"## Case Summary: {case['case_number']}\n\n"
                f"- Claim Number: {case.get('claim_number', 'N/A')}\n"
                f"- Provider: {case.get('provider', 'N/A')}\n"
                f"- Insured: {case.get('insured', 'N/A')}\n"
                f"- Date of Loss: {case.get('date_of_loss', 'N/A')}\n"
                f"- Status: {case.get('status', 'N/A')}\n"
                f"- Created on: {case.get('createdtime', 'N/A')}\n"
            )
            
            # Add comment summary
            if comments_df.empty:
                formatted_answer += "\n**No comments found for this case.**"
            else:
                formatted_answer += f"\n### Recent Comments ({len(comments_df)} found):\n\n"
                
                for i, comment in enumerate(comments_df.iterrows(), 1):
                    row = comment[1]
                    content = row['commentcontent']
                    creator = row['creator_name'] if pd.notna(row['creator_name']) else "Unknown"
                    date = row['createdtime'] if pd.notna(row['createdtime']) else "Unknown date"
                    
                    # Truncate long comments
                    if len(content) > 200:
                        content = content[:197] + "..."
                    
                    formatted_answer += f"**Comment {i}** - by {creator} on {date}:\n{content}\n\n"
                    
                    # Limit to first 3 comments to avoid overlong responses
                    if i >= 3:
                        remaining = len(comments_df) - 3
                        if remaining > 0:
                            formatted_answer += f"*...and {remaining} more comments*"
                        break
            
            # Generate URL for the case
            url = self.url_generator.generate_url('cases', int(case['recordid']))
            
            return {
                "answer": formatted_answer,
                "recordid": int(case['recordid']),
                "link": url
            }
            
        except Exception as e:
            logging.error(f"Error handling case summary: {str(e)}")
            return {
                "answer": f"Error retrieving case summary: {str(e)}",
                "recordid": None,
                "link": None
            }
        
    def _is_comment_summary_request(self, question: str) -> bool:
        """Determine if the question is asking for a comment summary"""
        comment_keywords = [
            'comment summary', 'summarize comments', 'comment highlights',
            'what do the comments say', 'summary of comments', 'case comments',
            'show me the comments', 'extract from comments', 'comment extraction',
            'case summary', 'summary of case', 'summarize case', 'case details', 'show me case'
        ]
        
        question_lower = question.lower()
        
        # Check for comment keywords
        has_comment_keyword = any(keyword in question_lower for keyword in comment_keywords)
        
        # Check for case identifiers using a broader pattern to catch more formats
        case_pattern = r'(case|CS|PDC)\s*[-:]?\s*(\w+[-]?\d+)'
        has_case_identifier = re.search(case_pattern, question, re.IGNORECASE) is not None
        
        return has_comment_keyword or has_case_identifier
    
    def _handle_case_summary_query(self, question: str) -> dict:
        """Handle queries requesting case or comment summaries"""
        try:
            # Extract case number or ID
            case_pattern = r'(case|CS|PDC)\s*[-:]?\s*(\w+[-]?\d+)'
            case_match = re.search(case_pattern, question, re.IGNORECASE)
            
            if not case_match:
                return {
                    "answer": "I couldn't identify a case number in your request. Please specify a case number like 'PDC22-109768'.",
                    "recordid": None,
                    "link": None
                }
            
            case_id = case_match.group(2)
            logging.info(f"Looking for case with identifier: {case_id}")
            
            # Query to get case details
            query = """
            SELECT 
                c.casesid AS recordid,
                c.case_id,
                c.case_number,
                c.claim_number,
                IFNULL(p.provider_name, 'Not specified') AS provider,
                IFNULL(i.insured_name, 'Not specified') AS insured,
                c.date_of_loss,
                c.status,
                e.createdtime
            FROM u_yf_cases c
            JOIN vtiger_crmentity e ON c.casesid = e.crmid
            LEFT JOIN u_yf_providers p ON c.provider = p.providersid
            LEFT JOIN u_yf_insureds i ON c.insured = i.insuredsid
            WHERE (c.case_number = %s OR c.case_id = %s)
            AND e.deleted = 0
            LIMIT 1
            """
            
            df = self.db_manager.fetch_data_with_params(query, (case_id, case_id))
            
            if df.empty:
                return {
                    "answer": f"No case found with identifier: {case_id}",
                    "recordid": None,
                    "link": None
                }
            
            case = df.iloc[0]
            
            # Query for case comments
            comments_query = """
            SELECT 
                mc.commentcontent,
                u.name AS creator_name,
                e.createdtime
            FROM vtiger_modcomments mc
            JOIN vtiger_crmentity e ON mc.modcommentsid = e.crmid
            LEFT JOIN users u ON e.smcreatorid = u.id
            WHERE mc.related_to = %s
            AND e.deleted = 0
            ORDER BY e.createdtime DESC
            LIMIT 10
            """
            
            comments_df = self.db_manager.fetch_data_with_params(comments_query, (case['recordid'],))
            
            # Create case summary
            formatted_answer = (
                f"## Case Summary: {case['case_number']}\n\n"
                f"- Claim Number: {case.get('claim_number', 'N/A')}\n"
                f"- Provider: {case.get('provider', 'N/A')}\n"
                f"- Insured: {case.get('insured', 'N/A')}\n"
                f"- Date of Loss: {case.get('date_of_loss', 'N/A')}\n"
                f"- Status: {case.get('status', 'N/A')}\n"
                f"- Created on: {case.get('createdtime', 'N/A')}\n"
            )
            
            # Add comment summary
            if comments_df.empty:
                formatted_answer += "\n**No comments found for this case.**"
            else:
                formatted_answer += f"\n### Recent Comments ({len(comments_df)} found):\n\n"
                
                for i, comment in enumerate(comments_df.iterrows(), 1):
                    row = comment[1]
                    content = row['commentcontent']
                    creator = row['creator_name'] if pd.notna(row['creator_name']) else "Unknown"
                    date = row['createdtime'] if pd.notna(row['createdtime']) else "Unknown date"
                    
                    # Truncate long comments
                    if len(content) > 200:
                        content = content[:197] + "..."
                    
                    formatted_answer += f"**Comment {i}** - by {creator} on {date}:\n{content}\n\n"
                    
                    # Limit to first 3 comments to avoid overlong responses
                    if i >= 3:
                        remaining = len(comments_df) - 3
                        if remaining > 0:
                            formatted_answer += f"*...and {remaining} more comments*"
                        break
            
            # Generate URL for the case
            url = self.url_generator.generate_url('cases', int(case['recordid']))
            
            return {
                "answer": formatted_answer,
                "recordid": int(case['recordid']),
                "link": url
            }
            
        except Exception as e:
            logging.error(f"Error handling case summary: {str(e)}")
            return {
                "answer": f"Error retrieving case summary: {str(e)}",
                "recordid": None,
                "link": None
            }

    def initialize_tables(self):
        """Initialize all tables from config"""
        try:
            from config import TABLES_CONFIG
            logging.info("Skipping table initialization - focusing on report functionality")
            # Skip actual initialization
            return
            
            # The original code below is commented out
            # for table_name, columns in TABLES_CONFIG.items():
            #    try:
            #        self.initialize_table(table_name, columns)
            #        logging.info(f"Initialized table: {table_name}")
            #    except Exception as e:
            #        logging.error(f"Failed to initialize table {table_name}: {str(e)}")
        except Exception as e:
            logging.error(f"Error in initialize_tables: {str(e)}")