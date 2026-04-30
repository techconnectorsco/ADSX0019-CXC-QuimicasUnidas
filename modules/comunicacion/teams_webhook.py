# modules/comunicacion/teams_webhook.py
"""
Teams Webhook Notifier
Envía notificaciones y reportes al canal de Teams configurado
"""

import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from config.settings import settings


class TeamsNotifier:
    """
    Cliente para enviar notificaciones a Microsoft Teams via Webhook.
    
    Uso básico:
        notifier = TeamsNotifier()
        notifier.send_simple("Hola desde el RPA!")
        notifier.send_execution_report(success=True, details={...})
    """
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or getattr(settings, 'TEAMS_WEBHOOK_URL', None)
        
        if not self.webhook_url:
            raise ValueError(
                "No se encontró URL del webhook de Teams. "
                "Configura TEAMS_WEBHOOK_URL en el archivo .env"
            )
    
    def _send_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Envía un payload JSON al webhook de Teams."""
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                return {'success': True, 'message': 'Mensaje enviado correctamente'}
            else:
                return {
                    'success': False, 
                    'error': f'HTTP {response.status_code}: {response.text}'
                }
                
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Timeout al conectar con Teams'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': str(e)}
    
    def send_simple(self, message: str) -> Dict[str, Any]:
        """Envía un mensaje de texto simple."""
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": message,
                                "wrap": True
                            }
                        ]
                    }
                }
            ]
        }
        return self._send_payload(payload)
    
    def send_execution_report(
        self,
        process_name: str,
        success: bool,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        records_processed: int = 0,
        records_success: int = 0,
        records_failed: int = 0,
        details: Optional[str] = None,
        errors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Envía un reporte de ejecución del RPA con formato profesional."""
        end_time = end_time or datetime.now()
        duration = end_time - start_time
        duration_str = str(duration).split('.')[0]
        
        accent_color = "Good" if success else "Attention"
        status_emoji = "✅" if success else "❌"
        status_text = "COMPLETADO" if success else "CON ERRORES"
        
        body = [
            {
                "type": "TextBlock",
                "text": f"🤖 Reporte de Ejecución - {process_name}",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{status_emoji} {status_text}",
                                "weight": "Bolder",
                                "color": accent_color,
                                "size": "Medium"
                            }
                        ]
                    }
                ]
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "📅 Fecha", "value": start_time.strftime("%d/%m/%Y")},
                    {"title": "🕐 Inicio", "value": start_time.strftime("%H:%M:%S")},
                    {"title": "🕑 Fin", "value": end_time.strftime("%H:%M:%S")},
                    {"title": "⏱️ Duración", "value": duration_str}
                ]
            }
        ]
        
        if records_processed > 0:
            body.append({
                "type": "TextBlock",
                "text": "📊 Estadísticas",
                "weight": "Bolder",
                "spacing": "Medium"
            })
            body.append({
                "type": "FactSet",
                "facts": [
                    {"title": "Total procesados", "value": str(records_processed)},
                    {"title": "✅ Exitosos", "value": str(records_success)},
                    {"title": "❌ Fallidos", "value": str(records_failed)}
                ]
            })
        
        if details:
            body.append({
                "type": "TextBlock",
                "text": "📝 Detalles",
                "weight": "Bolder",
                "spacing": "Medium"
            })
            body.append({
                "type": "TextBlock",
                "text": details,
                "wrap": True,
                "size": "Small"
            })
        
        if errors and len(errors) > 0:
            body.append({
                "type": "TextBlock",
                "text": "⚠️ Errores Encontrados",
                "weight": "Bolder",
                "color": "Attention",
                "spacing": "Medium"
            })
            for error in errors[:5]:
                body.append({
                    "type": "TextBlock",
                    "text": f"• {error}",
                    "wrap": True,
                    "size": "Small",
                    "color": "Attention"
                })
            if len(errors) > 5:
                body.append({
                    "type": "TextBlock",
                    "text": f"... y {len(errors) - 5} errores más",
                    "size": "Small",
                    "isSubtle": True
                })
        
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body
                    }
                }
            ]
        }
        
        return self._send_payload(payload)
    
    def send_cxc_summary(
        self,
        total_clientes: int,
        enviados: int,
        excluidos: int,
        errores: int,
        monto_total_crc: float = 0,
        monto_total_usd: float = 0
    ) -> Dict[str, Any]:
        """Envía un resumen específico para el proceso de CXC."""
        body = [
            {
                "type": "TextBlock",
                "text": "📧 Resumen Envío Estados de Cuenta",
                "weight": "Bolder",
                "size": "Large"
            },
            {
                "type": "TextBlock",
                "text": datetime.now().strftime("Ejecución: %d/%m/%Y %H:%M"),
                "isSubtle": True,
                "size": "Small"
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(total_clientes),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "horizontalAlignment": "Center"
                            },
                            {
                                "type": "TextBlock",
                                "text": "Total Clientes",
                                "horizontalAlignment": "Center",
                                "size": "Small"
                            }
                        ]
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(enviados),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Good",
                                "horizontalAlignment": "Center"
                            },
                            {
                                "type": "TextBlock",
                                "text": "Enviados",
                                "horizontalAlignment": "Center",
                                "size": "Small"
                            }
                        ]
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(excluidos),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Warning",
                                "horizontalAlignment": "Center"
                            },
                            {
                                "type": "TextBlock",
                                "text": "Excluidos",
                                "horizontalAlignment": "Center",
                                "size": "Small"
                            }
                        ]
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(errores),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Attention",
                                "horizontalAlignment": "Center"
                            },
                            {
                                "type": "TextBlock",
                                "text": "Errores",
                                "horizontalAlignment": "Center",
                                "size": "Small"
                            }
                        ]
                    }
                ]
            }
        ]
        
        if monto_total_crc > 0 or monto_total_usd > 0:
            facts = []
            if monto_total_crc > 0:
                facts.append({
                    "title": "💰 Total CRC",
                    "value": f"₡{monto_total_crc:,.2f}"
                })
            if monto_total_usd > 0:
                facts.append({
                    "title": "💵 Total USD",
                    "value": f"${monto_total_usd:,.2f}"
                })
            
            body.append({
                "type": "FactSet",
                "facts": facts,
                "spacing": "Medium"
            })
        
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body
                    }
                }
            ]
        }
        
        return self._send_payload(payload)
    
    def send_agent_report_summary(
        self,
        total_agentes: int,
        reportes_enviados: int,
        total_clientes_gira: int
    ) -> Dict[str, Any]:
        """Envía resumen del reporte de giras para agentes (martes)."""
        body = [
            {
                "type": "TextBlock",
                "text": "🚗 Resumen Reportes de Gira",
                "weight": "Bolder",
                "size": "Large"
            },
            {
                "type": "TextBlock",
                "text": datetime.now().strftime("Ejecución: %d/%m/%Y %H:%M"),
                "isSubtle": True,
                "size": "Small"
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "👥 Total Agentes", "value": str(total_agentes)},
                    {"title": "📧 Reportes Enviados", "value": str(reportes_enviados)},
                    {"title": "🏢 Clientes en Gira", "value": str(total_clientes_gira)}
                ],
                "spacing": "Medium"
            }
        ]
        
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body
                    }
                }
            ]
        }
        
        return self._send_payload(payload)
    
    def send_error_alert(
        self,
        process_name: str,
        error_message: str,
        error_details: Optional[str] = None
    ) -> Dict[str, Any]:
        """Envía una alerta de error crítico."""
        body = [
            {
                "type": "TextBlock",
                "text": "🚨 ALERTA - Error en Automatización",
                "weight": "Bolder",
                "size": "Large",
                "color": "Attention"
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Proceso", "value": process_name},
                    {"title": "Fecha/Hora", "value": datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
                ]
            },
            {
                "type": "TextBlock",
                "text": "Error:",
                "weight": "Bolder",
                "spacing": "Medium"
            },
            {
                "type": "TextBlock",
                "text": error_message,
                "wrap": True,
                "color": "Attention"
            }
        ]
        
        if error_details:
            body.append({
                "type": "TextBlock",
                "text": "Detalles técnicos:",
                "weight": "Bolder",
                "spacing": "Medium",
                "size": "Small"
            })
            body.append({
                "type": "TextBlock",
                "text": error_details[:500],
                "wrap": True,
                "size": "Small",
                "isSubtle": True
            })
        
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body
                    }
                }
            ]
        }
        
        return self._send_payload(payload)


def notify(message: str) -> Dict[str, Any]:
    """Atajo para enviar un mensaje simple."""
    return TeamsNotifier().send_simple(message)