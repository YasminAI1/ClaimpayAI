# app/url_generator.py
from openpyxl.styles import PatternFill, Font
from datetime import datetime
import os
import re


class URLGenerator:
    BASE_URL = "https://pmcdev.claimpay.net/index.php"
    EXCEL_OUTPUT_DIR = "excel_exports"  # Local directory for Excel files
    
    # Updated mappings with proper ID field names for YetiForce schema
    URL_MAPPINGS = {
        'claims': {'module': 'Claims', 'prefix': 'CL_', 'id_field': 'claimsid'},
        'portfolios': {'module': 'Portfolios', 'prefix': 'PF_', 'id_field': 'portfoliosid'},
        'cases': {'module': 'Cases', 'prefix': 'CS_', 'id_field': 'casesid'},
        'collections': {'module': 'ClaimCollections', 'prefix': 'COL_', 'id_field': 'collectionsid'},
        'outside_cases': {'module': 'OutsideCases', 'prefix': 'OC_', 'id_field': 'outsidecasesid'}
    }
    
    def __init__(self):
        # Creates directory locally if it doesn't exist
        if not os.path.exists(self.EXCEL_OUTPUT_DIR):
            os.makedirs(self.EXCEL_OUTPUT_DIR)

    def generate_url(self, record_type: str, record_id: int) -> str:
        """
        Generate a URL for viewing a record in the CRM
        
        In YetiForce, the record ID in the URL is the same as the crmid in vtiger_crmentity,
        which matches with the primary key in each module table (e.g., claimsid, casesid)
        """
        if record_type not in self.URL_MAPPINGS:
            raise ValueError(f"Invalid record type: {record_type}")
            
        mapping = self.URL_MAPPINGS[record_type]
        return f"{self.BASE_URL}?module={mapping['module']}&view=Detail&record={record_id}"
    
    def get_excel_path(self, filename: str) -> str:
        """Generate local path for Excel file"""
        if not os.path.exists(self.EXCEL_OUTPUT_DIR):
            os.makedirs(self.EXCEL_OUTPUT_DIR)
        return os.path.join(self.EXCEL_OUTPUT_DIR, filename)