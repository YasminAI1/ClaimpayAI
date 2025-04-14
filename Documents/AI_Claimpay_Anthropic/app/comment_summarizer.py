# app/comment_summarizer.py
import pandas as pd
import logging
from typing import Dict, List, Any

class CommentSummarizer:
    """Summarizes comments for cases"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def get_case_comments(self, case_id: str) -> pd.DataFrame:
        """Get comments for a specified case"""
        try:
            # First get the case ID
            case_query = """
            SELECT casesid 
            FROM u_yf_cases
            WHERE case_id = %s OR case_number = %s
            LIMIT 1
            """
            
            case_df = self.db_manager.fetch_data_with_params(case_query, (case_id, case_id))
            
            if case_df.empty:
                logging.warning(f"No case found with ID: {case_id}")
                return pd.DataFrame()
                
            case_id_value = case_df.iloc[0]['casesid']
            
            # Then get comments
            comments_query = """
            SELECT 
                mc.commentcontent,
                u.name as author_name,
                e.createdtime
            FROM vtiger_modcomments mc
            JOIN vtiger_crmentity e ON mc.modcommentsid = e.crmid
            LEFT JOIN users u ON e.smcreatorid = u.id
            WHERE mc.related_to = %s
            AND e.deleted = 0
            ORDER BY e.createdtime DESC
            """
            
            return self.db_manager.fetch_data_with_params(comments_query, (case_id_value,))
            
        except Exception as e:
            logging.error(f"Error getting case comments: {str(e)}")
            return pd.DataFrame()
    
    def summarize_case_comments(self, case_id: str) -> Dict[str, Any]:
        """Summarize comments for a case"""
        try:
            # Get case details
            case_query = """
            SELECT 
                c.case_id,
                c.case_number,
                c.claim_number,
                p.provider_name,
                i.insured_name,
                c.date_of_loss,
                c.status,
                e.createdtime
            FROM u_yf_cases c
            JOIN vtiger_crmentity e ON c.casesid = e.crmid
            LEFT JOIN u_yf_providers p ON c.provider = p.providersid
            LEFT JOIN u_yf_insureds i ON c.insured = i.insuredsid
            WHERE c.case_id = %s OR c.case_number = %s
            AND e.deleted = 0
            LIMIT 1
            """
            
            case_df = self.db_manager.fetch_data_with_params(case_query, (case_id, case_id))
            
            if case_df.empty:
                return {
                    "success": False,
                    "message": f"No case found with ID: {case_id}"
                }
            
            case_details = case_df.iloc[0]
            
            # Get comments
            comments_df = self.get_case_comments(case_id)
            
            summary = {
                "success": True,
                "case_id": case_details.get('case_id', 'Unknown'),
                "case_number": case_details.get('case_number', 'Unknown'),
                "provider": case_details.get('provider_name', 'Unknown'),
                "insured": case_details.get('insured_name', 'Unknown'),
                "date_of_loss": case_details.get('date_of_loss', 'Unknown'),
                "status": case_details.get('status', 'Unknown'),
                "createdtime": case_details.get('createdtime', 'Unknown'),
                "comments_count": len(comments_df),
                "latest_comment_date": None,
                "comments": []
            }
            
            if not comments_df.empty:
                summary["latest_comment_date"] = comments_df.iloc[0]['createdtime']
                
                for _, comment in comments_df.iterrows():
                    summary["comments"].append({
                        "content": comment['commentcontent'],
                        "author": comment.get('author_name', 'Unknown'),
                        "date": comment['createdtime']
                    })
            
            return summary
            
        except Exception as e:
            logging.error(f"Error summarizing case comments: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }