# app.py
import sys
import os
from flask import Flask, render_template, request, jsonify, send_from_directory
import logging
from dotenv import load_dotenv
from app.hybrid_agent import HybridQuerySystem
from app.enhanced_rag import EnhancedRAGSystem
from config import DB_CONFIG, TABLES_CONFIG
from datetime import datetime
import threading
import schedule
import time

# Add the root directory to Python path to ensure all imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set API key if it's not already in environment variables
if 'ANTHROPIC_API_KEY' not in os.environ:
    os.environ['ANTHROPIC_API_KEY'] = "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"

# Configure logging and environment variables
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
load_dotenv()

# Create Flask application with explicit template folder
app = Flask(
    __name__, 
    static_folder='static',
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
)

# Configure Excel directory
EXCEL_FOLDER = 'excel_exports'  # Change this to match URLGenerator.EXCEL_OUTPUT_DIR
app.config['EXCEL_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_FOLDER)
os.makedirs(app.config['EXCEL_FOLDER'], exist_ok=True)

# Initialize systems
hybrid_system = HybridQuerySystem(DB_CONFIG)
rag_system = EnhancedRAGSystem(DB_CONFIG)

def refresh_views_job():
    """Job to refresh materialized views"""
    try:
        logging.info("Refreshing report views")
        # Use the database manager from the RAG system
        rag_system.db_manager.refresh_report_views()
    except Exception as e:
        logging.error(f"Error in view refresh job: {str(e)}")

def run_scheduler():
    """Run the scheduler in a background thread"""
    schedule.every().day.at("03:00").do(refresh_views_job)  # Run at 3 AM
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index.html')

@app.route('/query', methods=['POST'])
def query():
    try:
        user_question = request.form['query']
        logging.info(f"Received question: {user_question}")

        # Skip regular RAG execution for excel reports
        if 'excel' in user_question.lower() or 'report' in user_question.lower():
            # Direct call to report engine
            result = rag_system.report_engine.generate_report(user_question)
            
            if result.get('is_excel'):
                excel_url = f"/excel_exports/{result['excel_path']}"
                
                # Simple response without preview
                formatted_response = (
                    f"{result['answer']}\n\n"
                    f"<a href='{excel_url}' class='excel-download' target='_blank'>"
                    f"📊 Download Complete Results in Excel</a>"
                )
                
                return jsonify({
                    'response': formatted_response,
                    'type': 'excel',
                    'excel_url': excel_url
                })
        
        # For other queries, use the regular handler
        result = rag_system.query(user_question)
        
        if result.get('link'):
            formatted_response = (
                f"{result['answer']}\n"
                f"<a href='{result['link']}' target='_blank'>View Details →</a>"
            )
            
            return jsonify({
                'response': formatted_response,
                'type': 'semantic',
                'link': result['link']
            })

        # Handle other responses
        return jsonify({
            'response': result.get('answer', 'No response generated'),
            'type': 'semantic'
        })

    except Exception as e:
        logging.error(f"Query error: {str(e)}", exc_info=True)
        return jsonify({
            'response': "An error occurred while processing your request.",
            'error': str(e)
        }), 500
    
@app.route('/excel_exports/<filename>')
def download_file(filename):
    """Handle Excel file downloads"""
    try:
        # Make sure the Excel directory exists
        os.makedirs(app.config['EXCEL_FOLDER'], exist_ok=True)
        
        # Check if the file exists
        filepath = os.path.join(app.config['EXCEL_FOLDER'], filename)
        if not os.path.isfile(filepath):
            logging.error(f"Excel file not found: {filepath}")
            return "Excel file not found", 404
            
        # Log download request
        logging.info(f"Serving Excel file: {filename}")
        
        # Return the file
        return send_from_directory(
            app.config['EXCEL_FOLDER'],
            filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        return f"Error downloading file: {str(e)}", 500

@app.route('/view/<module>/<int:record_id>')
def view_record(module, record_id):
    """Handle viewing a specific record"""
    try:
        # Query the database for record details
        if module.lower() == 'claims':
            query = """
            SELECT * FROM u_yf_claims c
            JOIN vtiger_crmentity e ON c.claimsid = e.crmid
            WHERE c.claimsid = %s AND e.deleted = 0
            """
        elif module.lower() == 'cases':
            query = """
            SELECT * FROM u_yf_cases c
            JOIN vtiger_crmentity e ON c.casesid = e.crmid
            WHERE c.casesid = %s AND e.deleted = 0
            """
        # Add other modules as needed
        else:
            return f"Unknown module: {module}", 404
            
        record = rag_system.db_manager.fetch_data_with_params(query, (record_id,))
        
        if record.empty:
            return f"Record {record_id} not found in module {module}", 404
            
        # Render a template with the record data
        return render_template('record_detail.html', 
                              module=module, 
                              record_id=record_id,
                              data=record.iloc[0].to_dict())
                              
    except Exception as e:
        logging.error(f"Error viewing record: {str(e)}")
        return f"Error: {str(e)}", 500

# Create templates directory if it doesn't exist
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'), exist_ok=True)

if __name__ == '__main__':
    try:
        # Start the scheduler thread
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
        # Try to initialize tables, but continue even if it fails
        rag_system.initialize_tables()
    except Exception as e:
        logging.warning(f"Table initialization failed, but continuing: {str(e)}")
    
    # Run Flask app
    app.run(debug=False, host='127.0.0.1', port=5000)