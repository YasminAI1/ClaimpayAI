# app/report_engine.py
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from langchain_anthropic import ChatAnthropic

class ReportEngine:
    """Enhanced engine for generating report queries and Excel exports with Claude integration"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.excel_dir = "excel_exports"    
        os.makedirs(self.excel_dir, exist_ok=True)
        
        # Initialize Claude model if API key available
        try:
            anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY')
            if anthropic_api_key:
                self.llm = ChatAnthropic(
                    model="claude-3-sonnet-20240229", 
                    temperature=0,
                    anthropic_api_key=anthropic_api_key
                )
                logging.info("Claude integration initialized successfully")
            else:
                self.llm = None
                logging.warning("No ANTHROPIC_API_KEY found - Claude features disabled")
        except Exception as e:
            logging.error(f"Claude initialization error: {str(e)}")
            self.llm = None
            
        # Initialize comment summarizer with Claude capabilities
        try:
            if self.llm:
                logging.info("Claude integration initialized for comment summarization")
        except Exception as e:
            logging.error(f"Comment summarization setup error: {str(e)}")
    
    def extract_report_parameters(self, question: str) -> Dict[str, Any]:
        """Extract report parameters using regular expressions"""
        params = {
            'provider': None,
            'date_of_loss_before': None,
            'investor': None,
            'funded_last_month': False,
            'report_type': 'provider_claims'
        }
        
        # Extract provider name
        provider_patterns = [
            r'provider\s+(?:is\s+)?(\d+)',  # Numeric ID: "provider is 981"
            r'provider\s+(\w+\s*\w*)',      # Name: "provider AQA"
            r'claims of\s+([^\.]+)',        # "claims of Provider name"
            r'of\s+provider\s+([^\.]+)'     # "of Provider name"
        ]
        
        for pattern in provider_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                provider = match.group(1).strip()
                params['provider'] = provider
                break
        
        # Extract date
        date_patterns = [
            r'before\s+(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
            r'before\s+(\d{4}-\d{1,2}-\d{1,2})'   # YYYY-MM-DD
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    if '/' in date_str:
                        month, day, year = date_str.split('/')
                        params['date_of_loss_before'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    else:
                        params['date_of_loss_before'] = date_str
                except Exception as e:
                    logging.warning(f"Error parsing date {date_str}: {str(e)}")
                break
                
        # Extract investor
        investor_patterns = [
            r'investor\s+(?:is\s+)?(\d+)',  # Numeric ID
            r'investor\s+(\w+\s*\w*)',      # Name
            r'funded by\s+([^\.]+)'         # "funded by X"
        ]
        
        for pattern in investor_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                investor = match.group(1).strip()
                params['investor'] = investor
                break
                
        # Check for "last month"
        if re.search(r'last month|previous month', question, re.IGNORECASE):
            params['funded_last_month'] = True
            
        return params
        
    def build_report_query(self, params: Dict[str, Any]) -> Tuple[str, Tuple]:
        """Build a parameterized query with proper joins based on the parameters"""
        # Simple query that works with the new database structure
        query = """
            SELECT 
                c.claimsid AS recordid,
                c.claim_id,
                c.claim_number,
                c.date_of_loss,
                c.date_of_service,
                c.claim_status,
                p.provider_name AS provider_name,
                IFNULL(i.insured_name, c.insured) AS insured_name,
                e.createdtime
            FROM u_yf_claims c
            JOIN vtiger_crmentity e ON c.claimsid = e.crmid
            JOIN u_yf_providers p ON c.provider = p.providersid
            LEFT JOIN u_yf_insureds i ON c.insured = i.insuredsid
        """
        
        where_clauses = ["e.deleted = 0"]
        query_params = []
        
        # Add provider filter
        if params.get('provider'):
            where_clauses.append("p.provider_name LIKE %s")
            query_params.append(f"%{params['provider']}%")
        
        # Add purchased filter
        if params.get('report_type') == 'provider_claims':
            where_clauses.append("c.claim_status = %s")
            query_params.append('Purchased')
        
        # Add date filter
        if params.get('date_of_loss_before'):
            where_clauses.append("c.date_of_loss < %s")
            query_params.append(params['date_of_loss_before'])
        
        # Add WHERE clause if needed
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Add ORDER BY
        query += " ORDER BY c.date_of_loss DESC"
        
        # Log the query for debugging
        log_query = query
        for param in query_params:
            log_query = log_query.replace('%s', f"'{param}'", 1)
        logging.info(f"Final query: {log_query}")
        
        return query, tuple(query_params)
        
    def generate_report(self, question: str) -> Dict[str, Any]:
        """Generate a report based on user question"""
        try:
            # Extract parameters from the question
            params = self.extract_report_parameters(question)
            logging.info(f"Extracted report parameters: {params}")
            
            # Build the query
            query, query_params = self.build_report_query(params)
            
            # Execute the query
            logging.info(f"Executing query: {query} with params: {query_params}")
            df = self.db_manager.fetch_data_with_params(query, query_params)
            
            if df.empty:
                return {
                    "answer": f"No records found matching your criteria.",
                    "is_excel": False
                }
            
            # Create Excel file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            excel_filename = f"report_{timestamp}.xlsx"
            excel_path = os.path.join(self.excel_dir, excel_filename)
            
            # Export to Excel
            self._export_to_excel(df, excel_path, params)
            
            # Return the result
            return {
                "answer": f"Generated report for {params.get('provider', 'your criteria')} with {len(df)} records.",
                "is_excel": True,
                "excel_path": excel_filename,
                "data": df.to_dict('records'),
                "skip_preview_generation": True
            }
            
        except Exception as e:
            logging.error(f"Error generating report: {str(e)}", exc_info=True)
            return {
                "answer": f"An error occurred generating the report: {str(e)}",
                "is_excel": False
            }
    
    def _export_to_excel(self, df: pd.DataFrame, filepath: str, params: Dict[str, Any]) -> None:
        """Export data to Excel with proper formatting"""
        try:
            # Create a new workbook and get the active worksheet
            wb = Workbook()
            ws = wb.active
            ws.title = "Report"
            
            # Add a title
            title = "Claims Report"
            if params.get('provider'):
                title += f" - {params['provider']}"
            
            ws.merge_cells('A1:F1')
            title_cell = ws['A1']
            title_cell.value = title
            title_cell.font = Font(size=16, bold=True)
            title_cell.alignment = Alignment(horizontal='center')
            
            # Add generated timestamp
            ws.merge_cells('A2:F2')
            timestamp_cell = ws['A2']
            timestamp_cell.value = f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            timestamp_cell.font = Font(italic=True)
            timestamp_cell.alignment = Alignment(horizontal='center')
            
            # Add headers at row 4
            headers = list(df.columns)
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=4, column=col_idx)
                cell.value = header.replace('_', ' ').upper()
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                cell.alignment = Alignment(horizontal='center')
            
            # Write data starting at row A5
            for row_idx, row in enumerate(df.values, 5):
                for col_idx, value in enumerate(row, 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    
                    # Handle datetime values
                    if isinstance(value, pd.Timestamp):
                        cell.value = value.strftime('%Y-%m-%d')
                    else:
                        cell.value = value
                        
                    # Add zebra striping
                    if row_idx % 2 == 0:
                        cell.fill = PatternFill(start_color="EFF3F8", end_color="EFF3F8", fill_type="solid")
            
            # Auto-adjust column widths
            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                
                adjusted_width = max(max_length + 2, 10)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            # Save the workbook
            wb.save(filepath)
            logging.info(f"Excel report saved to {filepath}")
            
        except Exception as e:
            logging.error(f"Error exporting to Excel: {str(e)}")
            raise
    