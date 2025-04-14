# app/schema_inspector.py
import logging
from typing import Dict, List, Any, Optional, Union, Set
import re
import pandas as pd

class SchemaInspector:
    """
    Class to inspect database schema and provide information about tables, columns, and relationships
    """
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.schema_cache = {}
        self.relationships = {}
        self.id_mappings = {}
        self._initialize_schema()
        
    def _initialize_schema(self):
        """Initialize schema information"""
        try:
            # Get list of tables
            query = "SHOW TABLES"
            tables_df = self.db_manager.fetch_data(query)
            
            if tables_df.empty:
                logging.warning("No tables found in database")
                return
                
            # Process each table
            tables_column = tables_df.columns[0]  # Usually 'Tables_in_dbname'
            for table_name in tables_df[tables_column]:
                # Skip system tables
                if table_name.startswith('vtiger_') and table_name != 'vtiger_crmentity':
                    continue
                    
                # Get columns for this table
                self._cache_table_schema(table_name)
                
            # Establish relationships
            self._detect_relationships()
            
            logging.info(f"Schema initialized with {len(self.schema_cache)} tables")
            
        except Exception as e:
            logging.error(f"Error initializing schema: {str(e)}")
            
    def _cache_table_schema(self, table_name: str):
        """Cache schema information for a table"""
        try:
            # Get columns
            columns_query = f"SHOW COLUMNS FROM {table_name}"
            columns_df = self.db_manager.fetch_data(columns_query)
            
            if columns_df.empty:
                return
                
            # Store column information
            columns_info = {}
            primary_key = None
            
            for _, row in columns_df.iterrows():
                field = row['Field']
                field_type = row['Type']
                is_primary = row['Key'] == 'PRI'
                
                if is_primary:
                    primary_key = field
                    
                columns_info[field] = {
                    'type': field_type,
                    'is_primary': is_primary,
                    'nullable': row['Null'] == 'YES'
                }
            
            # Store in cache
            self.schema_cache[table_name] = {
                'columns': columns_info,
                'primary_key': primary_key
            }
            
            # Check if this is an entity table (has id/name relationship)
            self._detect_id_name_mapping(table_name)
            
        except Exception as e:
            logging.error(f"Error caching schema for {table_name}: {str(e)}")
            
    def _detect_relationships(self):
        """Detect relationships between tables based on column names"""
        for table_name, schema in self.schema_cache.items():
            columns = schema['columns']
            
            for column_name in columns:
                # Check if column looks like a foreign key (ends with 'id' but not the primary key)
                if (column_name.endswith('id') or column_name.endswith('Id')) and column_name != schema['primary_key']:
                    # Try to find the referenced table
                    potential_ref_table = self._find_referenced_table(column_name)
                    
                    if potential_ref_table:
                        if table_name not in self.relationships:
                            self.relationships[table_name] = {}
                            
                        self.relationships[table_name][column_name] = potential_ref_table
        
    def _find_referenced_table(self, column_name: str) -> Optional[str]:
        """Find the table referenced by a column name"""
        # Remove 'id' suffix
        base_name = column_name[:-2] if column_name.endswith('id') else column_name[:-2]
        
        # Try pluralized and singular forms
        potential_tables = [
            f"u_yf_{base_name}s",  # pluralized
            f"u_yf_{base_name}"    # singular
        ]
        
        for table in potential_tables:
            if table in self.schema_cache:
                return table
                
        return None
        
    def _detect_id_name_mapping(self, table_name: str):
        """
        Detect if a table has an ID-name mapping (e.g. providersid -> provider_name)
        """
        columns = self.schema_cache[table_name]['columns']
        primary_key = self.schema_cache[table_name]['primary_key']
        
        if not primary_key:
            return
            
        # Look for name columns
        name_columns = [col for col in columns if 'name' in col.lower()]
        
        if name_columns:
            self.id_mappings[table_name] = {
                'id_column': primary_key,
                'name_column': name_columns[0]  # Use the first name column
            }
            
    def get_column_info(self, table_name: str, column_name: str) -> Optional[Dict]:
        """Get information about a specific column"""
        if table_name in self.schema_cache:
            if column_name in self.schema_cache[table_name]['columns']:
                return self.schema_cache[table_name]['columns'][column_name]
        return None
    
    def get_table_columns(self, table_name: str) -> List[str]:
        """Get list of columns for a table"""
        if table_name in self.schema_cache:
            return list(self.schema_cache[table_name]['columns'].keys())
        return []
    
    def get_primary_key(self, table_name: str) -> Optional[str]:
        """Get primary key for a table"""
        if table_name in self.schema_cache:
            return self.schema_cache[table_name]['primary_key']
        return None
    
    def get_related_tables(self, table_name: str) -> Dict[str, str]:
        """Get tables related to this one"""
        if table_name in self.relationships:
            return self.relationships[table_name]
        return {}
    
    def get_name_column(self, table_name: str) -> Optional[str]:
        """Get the name column for an ID mapping"""
        if table_name in self.id_mappings:
            return self.id_mappings[table_name]['name_column']
        return None
    
    def get_id_column(self, table_name: str) -> Optional[str]:
        """Get the ID column for an ID mapping"""
        if table_name in self.id_mappings:
            return self.id_mappings[table_name]['id_column']
        return None
    
    def find_table_for_entity(self, entity_name: str) -> Optional[str]:
        """Find the table that corresponds to an entity name (e.g. 'provider' -> 'u_yf_providers')"""
        # Try various forms of the entity name
        singular = entity_name.lower().rstrip('s')
        plural = f"{singular}s"
        
        potential_tables = [
            f"u_yf_{plural}",
            f"u_yf_{singular}"
        ]
        
        for table in potential_tables:
            if table in self.schema_cache:
                return table
                
        return None
    
    def has_column(self, table_name: str, column_name: str) -> bool:
        """Check if a table has a particular column"""
        if table_name in self.schema_cache:
            return column_name in self.schema_cache[table_name]['columns']
        return False