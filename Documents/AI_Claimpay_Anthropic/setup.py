# setup.py
from setuptools import setup, find_packages

setup(
    name="ai_claimpay",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'flask',
        'langchain',
        'langchain_anthropic',
        'sqlalchemy',
        'pandas',
        'python-dotenv',
        'mysql-connector-python',
    ],
)