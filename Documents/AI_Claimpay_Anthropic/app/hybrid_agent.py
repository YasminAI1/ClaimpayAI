# app/hybrid_agent.py
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_anthropic import ChatAnthropic
from langchain.agents.agent_types import AgentType
from typing import Dict, Any, Optional
import logging

class HybridQuerySystem:
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.connection_string = f"mysql+mysqlconnector://{db_config['user']}:{db_config['password']}@{db_config['host']}/{db_config['database']}"
        self.db = SQLDatabase.from_uri(self.connection_string)
        self.llm = ChatAnthropic(temperature=0, model="claude-3-sonnet-20240229")
        self.agent = self._create_agent()
        
    def _create_agent(self):
        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        return create_sql_agent(
            llm=self.llm,
            toolkit=toolkit,
            verbose=True,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION
        )
    
    def _is_analytical_query(self, question: str) -> bool:
        analytical_keywords = [
            'how many', 'count', 'total', 'average', 'sum',
            'minimum', 'maximum', 'first', 'last', 'compare',
            'difference', 'percentage', 'ratio', 'group by',
            'order by', 'between', 'greater than', 'less than'
        ]
        return any(keyword in question.lower() for keyword in analytical_keywords)
    
    def process_query(self, question: str) -> Dict[str, Any]:
        try:
            if self._is_analytical_query(question):
                result = self.agent.run(question)
                return {
                    'response': result,
                    'type': 'analytical',
                    'source': 'sql_agent'
                }
            else:
                return {
                    'response': None,
                    'type': 'semantic',
                    'source': 'vector_store'
                }
        except Exception as e:
            logging.error(f"Query processing error: {str(e)}")
            return {
                'response': f"Error processing query: {str(e)}",
                'type': 'error',
                'source': None
            }