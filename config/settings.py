# config/settings.py
"""
Configuración centralizada del Asistente Digital
Lee variables desde archivo .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class Settings:
    """Configuración de la aplicación."""
    
    # --- Base de Datos ---
    DB_SERVER: str = os.getenv('DB_SERVER', '')
    DB_DATABASE: str = os.getenv('DB_DATABASE', '')
    DB_USERNAME: str = os.getenv('DB_USERNAME', '')
    DB_PASSWORD: str = os.getenv('DB_PASSWORD', '')
    DB_PORT: int = int(os.getenv('DB_PORT', '1433'))
    
    # --- Microsoft Teams ---
    TEAMS_WEBHOOK_URL: str = os.getenv('TEAMS_WEBHOOK_URL', '')
    
    # --- Microsoft Graph API (Correos) - Para más adelante ---
    AZURE_TENANT_ID: str = os.getenv('AZURE_TENANT_ID', '')
    AZURE_CLIENT_ID: str = os.getenv('AZURE_CLIENT_ID', '')
    AZURE_CLIENT_SECRET: str = os.getenv('AZURE_CLIENT_SECRET', '')
    EMAIL_SENDER: str = os.getenv('EMAIL_SENDER', '')
    
    # --- General ---
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    TIMEZONE: str = os.getenv('TIMEZONE', 'America/Costa_Rica')
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == 'production'
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == 'development'
    
    @property
    def db_connection_string(self) -> str:
        """Genera el string de conexión ODBC."""
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.DB_SERVER},{self.DB_PORT};"
            f"DATABASE={self.DB_DATABASE};"
            f"UID={self.DB_USERNAME};"
            f"PWD={self.DB_PASSWORD}"
        )
    
    def validate_db_config(self) -> tuple[bool, list[str]]:
        """Valida que la configuración de BD esté completa."""
        missing = []
        if not self.DB_SERVER:
            missing.append('DB_SERVER')
        if not self.DB_DATABASE:
            missing.append('DB_DATABASE')
        if not self.DB_USERNAME:
            missing.append('DB_USERNAME')
        if not self.DB_PASSWORD:
            missing.append('DB_PASSWORD')
        
        return len(missing) == 0, missing
    
    def validate_teams_config(self) -> tuple[bool, list[str]]:
        """Valida que la configuración de Teams esté completa."""
        missing = []
        if not self.TEAMS_WEBHOOK_URL:
            missing.append('TEAMS_WEBHOOK_URL')
        
        return len(missing) == 0, missing


# Instancia global
settings = Settings()