# app/url_generator.py
class URLGenerator:
    BASE_URL = "https://pmcdev.claimpay.net/index.php"
    
    URL_MAPPINGS = {
        'claims': {'module': 'Claims', 'prefix': 'CL_'},
        'portfolios': {'module': 'Portfolios', 'prefix': 'PF_'},
        'cases': {'module': 'Cases', 'prefix': 'CS_'},
        'collections': {'module': 'ClaimCollections', 'prefix': 'COL_'},
        'outside_cases': {'module': 'OutsideCases', 'prefix': 'OC_'}
    }
    
    def generate_url(self, record_type: str, recordid: int) -> str:
        if record_type not in self.URL_MAPPINGS:
            raise ValueError(f"Invalid record type: {record_type}")
            
        mapping = self.URL_MAPPINGS[record_type]
        return f"{self.BASE_URL}?module={mapping['module']}&view=Detail&record={recordid}"
    
    def consume_get_token(url, headers=None):
    try:
        data = {
            "userName": azure_username,
            "password": azure_password
        }
        response = requests.post(url, headers=headers, data=data, verify=False)
        if response.status_code == 200:
            response_data = response.json()
            token = response_data.get('result', {}).get('token')
            if token:
                return token
            else:
                logger.info("Token not found in response.")
                return None
        else:
            logger.info(f"Error: Login request failed with status code {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None
----------------------------------

# Add these imports at the top of your file
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use environment variables for credentials
AZURE_USERNAME = os.getenv('AZURE_USERNAME')
AZURE_PASSWORD = os.getenv('AZURE_PASSWORD')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)