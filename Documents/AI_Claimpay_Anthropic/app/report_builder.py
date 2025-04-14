# app/report_builder.py
import logging
import re
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import pandas as pd
import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

class ReportBuilder:
    """
    Advanced report builder with field detection and auto-joining
    """
    
    def __init__(self, db_manager, schema_inspector):
        self.db_manager = db_manager
        self.schema = schema_inspector
        self.excel_dir = "excel_exports"
        os.makedirs(self.excel_dir, exist_ok=True)
        
    def extract_report_parameters(self, question: str) -> Dict[str, Any]:
        """Extract report parameters using regular expressions"""
        params = {
            'provider': None,
            'date_of_loss_before': None,
            'investor': None,
            'funded_last_month': False,
            'purchased': True,  # Default to purchased claims
            'main_entity': 'claims'  # Default entity
        }
        
        # Detect main entity (what are we reporting on?)
        if 'case' in question.lower() and not 'purchase' in question.lower():
            params['main_entity'] = 'cases'
        elif 'portfolio' in question.lower():
            params['main_entity'] = 'portfolios'
        
        # Extract provider
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
        
        # Extract date before
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
            r'investor\s+(?:is\s+)?(\d+)',        # Numeric ID
            r'investor\s+(\w+\s*\w*)',            # Name
            r'funded by\s+([^\.]+)',              # "funded by Investor X"
            r'by\s+investor\s+([^\.]+)'           # "by investor X"
        ]
        
        for pattern in investor_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                investor = match.group(1).strip()
                params['investor'] = investor
                break
        
        # Check for "last month" or "previous month"
        if re.search(r'last month|previous month', question, re.IGNORECASE):
            params['funded_last_month'] = True
        
        # Check if we're looking for purchased claims
        if not re.search(r'purchased', question, re.IGNORECASE):
            params['purchased'] = False
            
        return params
    
    def build_report_query(self, params: Dict[str, Any]) -> Tuple[str, tuple]:
        """
        Build a parameterized SQL query based on the extracted parameters,
        dynamically adapting to available fields and tables
        """
        main_entity = params.get('main_entity', 'claims')
        main_table = f"u_yf_{main_entity}"
        
        # Get primary key and alias
        primary_key = self.schema.get_primary_key(main_table)
        table_alias = main_entity[0]  # Use first letter as alias
        
        # Check if the main table exists
        if not main_table in self.schema.schema_cache:
            raise ValueError(f"Main table {main_table} not found in schema")
        
        # Start building the query
        select_columns = [f"{table_alias}.{primary_key} AS recordid"]
        joins = []
        where_clauses = []
        params_list = []
        
        # Always join with vtiger_crmentity to filter deleted records
        joins.append(f"JOIN vtiger_crmentity e ON {table_alias}.{primary_key} = e.crmid")
        where_clauses.append("e.deleted = 0")
        
        # Add main entity columns
        base_columns = [
            'claim_id', 'case_id', 'portfolio_id', 'claim_number', 'case_number',
            'date_of_loss', 'date_of_service', 'claim_status', 'status'
        ]
        
        for col in base_columns:
            if self.schema.has_column(main_table, col):
                select_columns.append(f"{table_alias}.{col}")
        
        # Process provider parameter
        if params.get('provider'):
            provider_value = params['provider']
            
            # Check if it's a numeric ID or a name
            if provider_value.isdigit():
                # It's a numeric ID
                provider_column = 'provider'
                if self.schema.has_column(main_table, provider_column):
                    where_clauses.append(f"{table_alias}.{provider_column} = %s")
                    params_list.append(provider_value)
            else:
                # It's a name - need to join with providers table
                provider_table = "u_yf_providers"
                provider_id_col = self.schema.get_primary_key(provider_table)
                provider_name_col = self.schema.get_name_column(provider_table)
                
                if provider_name_col:
                    # Add join with providers table
                    joins.append(f"JOIN {provider_table} p ON {table_alias}.provider = p.{provider_id_col}")
                    where_clauses.append(f"p.{provider_name_col} LIKE %s")
                    params_list.append(f"%{provider_value}%")
                    
                    # Add provider name to select
                    select_columns.append(f"p.{provider_name_col} AS provider_name")
        
        # Process date_of_loss_before parameter
        if params.get('date_of_loss_before'):
            date_col = 'date_of_loss'
            if self.schema.has_column(main_table, date_col):
                where_clauses.append(f"{table_alias}.{date_col} < %s")
                params_list.append(params['date_of_loss_before'])
        
        # Process investor parameter
        if params.get('investor'):
            investor_value = params['investor']
            
            # Join with portfolios and portfolio_purchases tables
            if main_entity == 'claims':
                # Need to join claims -> portfolios -> investors
                if self.schema.has_column(main_table, 'portfolio'):
                    joins.append("LEFT JOIN u_yf_portfolios pf ON c.portfolio = pf.portfoliosid")
                    
                    # Check if investors table exists
                    investors_table = "u_yf_investors"
                    if investors_table in self.schema.schema_cache:
                        investor_id_col = self.schema.get_primary_key(investors_table)
                        investor_name_col = self.schema.get_name_column(investors_table)
                        
                        if investor_name_col:
                            joins.append(f"LEFT JOIN {investors_table} inv ON pf.investor = inv.{investor_id_col}")
                            
                            # Add condition based on whether it's numeric or name
                            if investor_value.isdigit():
                                where_clauses.append(f"inv.{investor_id_col} = %s")
                                params_list.append(investor_value)
                            else:
                                where_clauses.append(f"inv.{investor_name_col} LIKE %s")
                                params_list.append(f"%{investor_value}%")
                                
                            # Add investor name to select
                            select_columns.append(f"inv.{investor_name_col} AS investor_name")
        
        # Process funded_last_month parameter
        if params.get('funded_last_month', False):
            # Calculate first and last day of previous month
            today = datetime.today()
            first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            last_day = today.replace(day=1) - timedelta(days=1)
            
            first_day_str = first_day.strftime('%Y-%m-%d')
            last_day_str = last_day.strftime('%Y-%m-%d')
            
            # Check if portfolio_purchases table exists and has funded_date
            pp_table = "u_yf_portfoliopurchases"
            if pp_table in self.schema.schema_cache and self.schema.has_column(pp_table, 'funded_date'):
                # Join with portfolio_purchases
                if main_entity == 'claims' and self.schema.has_column(main_table, 'portfolio_purchase'):
                    joins.append(f"LEFT JOIN {pp_table} pp ON {table_alias}.portfolio_purchase = pp.portfoliopurchasesid")
                    where_clauses.append("pp.funded_date BETWEEN %s AND %s")
                    params_list.extend([first_day_str, last_day_str])
                    
                    # Add funded_date to select
                    select_columns.append("pp.funded_date")
        
        # Handle purchased claims filter
        if params.get('purchased', True):
            status_col = 'claim_status' if main_entity == 'claims' else 'status'
            if self.schema.has_column(main_table, status_col):
                where_clauses.append(f"{table_alias}.{status_col} = %s")
                params_list.append('Purchased')
        
        # Add insured information
        if self.schema.has_column(main_table, 'insured'):
            insured_table = "u_yf_insureds"
            if insured_table in self.schema.schema_cache:
                insured_id_col = self.schema.get_primary_key(insured_table)
                insured_name_col = self.schema.get_name_column(insured_table)
                
                if insured_name_col:
                    joins.append(f"LEFT JOIN {insured_table} i ON {table_alias}.insured = i.{insured_id_col}")
                    select_columns.append(f"IFNULL(i.{insured_name_col}, {table_alias}.insured) AS insured_name")
        
        # Add createdtime
        select_columns.append("e.createdtime")
        
        # Build the final query
        query = f"""
        SELECT {', '.join(select_columns)}
        FROM {main_table} {table_alias}
        {' '.join(joins)}
        """
        
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"
            
        # Add order by
        date_col = 'date_of_loss' if self.schema.has_column(main_table, 'date_of_loss') else 'createdtime'
        query += f" ORDER BY {table_alias if date_col != 'createdtime' else 'e'}.{date_col} DESC"
        
        logging.info(f"Built query: {query}")
        logging.info(f"With parameters: {params_list}")
        
        return query, tuple(params_list)
        
    def generate_report(self, question: str) -> Dict[str, Any]:
        """
        Generate a report based on natural language question
        """
        try:
            # Extract parameters from the question
            params = self.extract_report_parameters(question)
            logging.info(f"Extracted report parameters: {params}")
            
            # Build the query
            query, query_params = self.build_report_query(params)
            
            # Execute the query
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
            
            # Export to Excel with styling
            self._export_to_excel(df, excel_path, params)
            
            # Create a descriptive title
            entity_type = params['main_entity'].rstrip('s').capitalize()
            
            title_parts = []
            title_parts.append(entity_type)
            
            if params.get('provider'):
                title_parts.append(f"for Provider {params['provider']}")
                
            if params.get('date_of_loss_before'):
                title_parts.append(f"before {params['date_of_loss_before']}")
                
            if params.get('investor'):
                title_parts.append(f"funded by {params['investor']}")
                
            if params.get('funded_last_month'):
                title_parts.append("funded last month")
                
            if params.get('purchased', True):
                title_parts.append("(Purchased)")
                
            report_title = " ".join(title_parts)
            
            return {
                "answer": f"Generated report with {len(df)} {params['main_entity']} records.",
                "is_excel": True,
                "excel_path": excel_filename,
                "data": df.to_dict('records'),
                "skip_preview_generation": True,  # Skip automatic preview generation
                "params": params
            }
            
        except Exception as e:
            logging.error(f"Error generating report: {str(e)}", exc_info=True)
            
            # Try a simplified query as fallback
            try:
                main_entity = params.get('main_entity', 'claims')
                table_name = f"u_yf_{main_entity}"
                primary_key = self.schema.get_primary_key(table_name)
                
                # Build a very simple query
                fallback_query = f"""
                SELECT t.*, e.createdtime
                FROM {table_name} t
                JOIN vtiger_crmentity e ON t.{primary_key} = e.crmid
                WHERE e.deleted = 0
                LIMIT 100
                """
                
                df = self.db_manager.fetch_data(fallback_query)
                
                if not df.empty:
                    # Create Excel file
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    excel_filename = f"fallback_report_{timestamp}.xlsx"
                    excel_path = os.path.join(self.excel_dir, excel_filename)
                    
                    df.to_excel(excel_path, index=False)
                    
                    return {
                        "answer": f"Error in main query, but generated fallback report with {len(df)} records. Limited to 100 records.",
                        "is_excel": True,
                        "excel_path": excel_filename,
                        "data": df.to_dict('records'),
                        "skip_preview_generation": True
                    }
            except Exception as inner_e:
                logging.error(f"Fallback query also failed: {str(inner_e)}")
            
            return {
                "answer": f"An error occurred while generating the report: {str(e)}",
                "is_excel": False
            }
            
    def _export_to_excel(self, df: pd.DataFrame, filepath: str, params: Dict[str, Any]) -> bool:
        """Export data to Excel with styling"""
        try:
            # Create workbook
            wb = Workbook()
            ws = wb.active
            
            # Set title
            entity_type = params['main_entity'].capitalize()
            title = f"{entity_type} Report"
            
            if params.get('provider'):
                title += f" - Provider: {params['provider']}"
            
            ws.title = entity_type
            
            # Add title and timestamp
            ws.merge_cells('A1:K1')
            title_cell = ws['A1']
            title_cell.value = title
            title_cell.font = Font(bold=True, size=14)
            title_cell.alignment = Alignment(horizontal='center')
            
            ws.merge_cells('A2:K2')
            timestamp_cell = ws['A2']
            timestamp_cell.value = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            timestamp_cell.font = Font(italic=True)
            timestamp_cell.alignment = Alignment(horizontal='center')
            
            # Add filter criteria
            row = 3
            if any(params.get(k) for k in ['provider', 'date_of_loss_before', 'investor', 'funded_last_month']):
                ws.merge_cells(f'A{row}:K{row}')
                criteria_cell = ws[f'A{row}']
                criteria_cell.value = "Filter Criteria:"
                criteria_cell.font = Font(bold=True)
                row += 1
                
                if params.get('provider'):
                    ws.merge_cells(f'A{row}:K{row}')
                    ws[f'A{row}'].value = f"Provider: {params['provider']}"
                    row += 1
                
                if params.get('date_of_loss_before'):
                    ws.merge_cells(f'A{row}:K{row}')
                    ws[f'A{row}'].value = f"Date of Loss Before: {params['date_of_loss_before']}"
                    row += 1
                
                if params.get('investor'):
                    ws.merge_cells(f'A{row}:K{row}')
                    ws[f'A{row}'].value = f"Investor: {params['investor']}"
                    row += 1
                
                if params.get('funded_last_month'):
                    ws.merge_cells(f'A{row}:K{row}')
                    ws[f'A{row}'].value = "Funded in Previous Month"
                    row += 1
                
                # Add extra space
                row += 1
            
            # Configure styles
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF")
            border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            # Write headers
            headers = list(df.columns)
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col)
                cell.value = header.upper().replace('_', ' ')
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center')
                cell.border = border
            
            # Format currency columns
            currency_columns = ['total_bill_amount', 'total_collections', 'purchase_value', 'hurdle']
            date_columns = ['date_of_loss', 'date_of_service', 'createdtime', 'funded_date', 'purchase_date']
            
            # Write data
            for data_row_idx, data_row in enumerate(df.values, row + 1):
                for col_idx, value in enumerate(data_row, 1):
                    cell = ws.cell(row=data_row_idx, column=col_idx)
                    
                    column_name = headers[col_idx - 1]
                    
                    # Format dates
                    if column_name in date_columns and value is not None:
                        if isinstance(value, (pd.Timestamp, datetime)):
                            cell.value = value.strftime('%Y-%m-%d') if hasattr(value, 'strftime') else value
                            cell.alignment = Alignment(horizontal='center')
                        else:
                            cell.value = value
                    # Format currency
                    elif column_name in currency_columns and value is not None:
                        try:
                            cell.value = float(value) if not pd.isna(value) else 0
                            cell.number_format = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)'
                        except (ValueError, TypeError):
                            cell.value = value
                    else:
                        cell.value = value
                    
                    # Add borders
                    cell.border = border
                    
                    # Add alternating row shading
                    if data_row_idx % 2 == 0:
                        cell.fill = PatternFill(start_color="E6F0FF", end_color="E6F0FF", fill_type="solid")
            
            # Adjust column widths
            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    try:
                        cell_length = len(str(cell.value))
                        if cell_length > max_length:
                            max_length = cell_length
                    except:
                        pass
                
                adjusted_width = max(max_length + 2, 12)  # Min width of 12
                ws.column_dimensions[column_letter].width = adjusted_width
            
            # Add totals row for numeric columns
            if not df.empty:
                total_row = len(df) + row + 1
                
                # Add "TOTAL" label
                ws.cell(row=total_row, column=1).value = "TOTAL"
                ws.cell(row=total_row, column=1).font = Font(bold=True)
                
                # Add sums for currency columns
                for col_name in currency_columns:
                    if col_name in headers:
                        col_idx = headers.index(col_name) + 1
                        cell = ws.cell(row=total_row, column=col_idx)
                        start_cell = f"{get_column_letter(col_idx)}{row+1}"
                        end_cell = f"{get_column_letter(col_idx)}{total_row-1}"
                        cell.value = f"=SUM({start_cell}:{end_cell})"
                        cell.font = Font(bold=True)
                        cell.number_format = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)'
                        cell.border = Border(top=Side(style='double'))
            
            # Save the workbook
            wb.save(filepath)
            logging.info(f"Successfully exported Excel file to {filepath}")
            return True
            
        except Exception as e:
            logging.error(f"Error exporting to Excel: {str(e)}")
            return False