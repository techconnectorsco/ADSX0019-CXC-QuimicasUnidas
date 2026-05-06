"""
sendEmailCXC.py - Químicas Unidas
Envío de correos electrónicos con Estados de Cuenta.

Usa Microsoft Graph API para enviar correos.
Credenciales en .env: TENANT_ID, CLIENT_ID, CLIENT_SECRET
"""

import os
import base64
import requests
from datetime import datetime
from typing import List, Dict, Optional

try:
    from msal import ConfidentialClientApplication
    MSAL_DISPONIBLE = True
except ImportError:
    MSAL_DISPONIBLE = False
    print("⚠️ msal no instalado. Ejecutar: pip install msal")

try:
    from decouple import config
    DECOUPLE_DISPONIBLE = True
except ImportError:
    DECOUPLE_DISPONIBLE = False
    print("⚠️ python-decouple no instalado. Ejecutar: pip install python-decouple")


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Credenciales Azure AD (cargar desde .env)
if DECOUPLE_DISPONIBLE:
    TENANT_ID = config('TENANT_ID', default='')
    CLIENT_ID = config('CLIENT_ID', default='')
    CLIENT_SECRET = config('CLIENT_SECRET', default='')
    SENDER_EMAIL = config('SENDER_EMAIL', default='boot@soportexperto.com')
else:
    TENANT_ID = os.environ.get('TENANT_ID', '')
    CLIENT_ID = os.environ.get('CLIENT_ID', '')
    CLIENT_SECRET = os.environ.get('CLIENT_SECRET', '')
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'boot@soportexperto.com')

# Rutas de imágenes
RUTA_LOGO = 'images/QU.png'
RUTA_FOOTER = 'images/footer.png'


# =============================================================================
# PLANTILLA HTML DEL CORREO
# =============================================================================

def get_email_html(nombre_cliente: str, datos: Dict = None) -> str:
    """
    Genera el HTML del correo de estado de cuenta.
    
    Args:
        nombre_cliente: Nombre del cliente destinatario
        datos: Datos del cliente (opcional, para personalización)
    
    Returns:
        String con el HTML del correo
    """
    # Resumen de saldos (si están disponibles)
    resumen_html = ""
    if datos:
        totales = datos.get('totales', {})
        if totales.get('dolares', 0) != 0 or totales.get('colones', 0) != 0:
            resumen_html = """
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 0; font-weight: bold; color: #0066cc; font-size: 16px;">Resumen de su cuenta:</p>
            """
            if totales.get('dolares', 0) != 0:
                resumen_html += f'<p style="margin: 5px 0; font-size: 15px;">• Saldo en Dólares: <strong>USD {totales["dolares"]:,.2f}</strong></p>'
            if totales.get('colones', 0) != 0:
                resumen_html += f'<p style="margin: 5px 0; font-size: 15px;">• Saldo en Colones: <strong>CRC {totales["colones"]:,.2f}</strong></p>'
            resumen_html += "</div>"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                color: #333333;
                background-color: #f4f4f4;
                margin: 0;
                padding: 0;
                line-height: 1.6;
            }}
            .container {{
                max-width: 900px; /* Ajustado de 700px a 900px para hacerlo más ancho */
                margin: 30px auto;
                background-color: #ffffff;
                padding: 40px 50px; /* Mayor margen interno para que no se vea pegado a los bordes */
                border-radius: 10px;
                box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 3px solid #28a0cc;
                margin-bottom: 25px;
            }}
            .header img {{
                max-width: 200px;
                height: auto;
            }}
            .content {{
                font-size: 15px;
            }}
            .highlight {{
                color: #0066cc;
                font-weight: bold;
                font-size: 16px;
            }}
            .policy-box {{
                background-color: #fdfaf0;
                border-left: 4px solid #f0ad4e;
                padding: 20px 25px;
                margin: 25px 0;
                border-radius: 0 8px 8px 0;
            }}
            .policy-box ul {{
                margin: 0;
                padding-left: 20px;
            }}
            .policy-box li {{
                margin-bottom: 12px;
                font-size: 14px;
            }}
            .contact-box {{
                background-color: #e3f2fd;
                padding: 25px;
                border-radius: 8px;
                margin-top: 30px;
                text-align: center;
                border: 1px solid #bbdefb;
            }}
            .contact-email {{
                font-size: 20px;
                font-weight: bold;
                color: #475da4;
                margin: 8px 15px;
                display: inline-block;
                text-decoration: none;
            }}
            .footer {{
                text-align: center;
                font-size: 12px;
                color: #666666;
                margin-top: 35px;
                padding-top: 20px;
                border-top: 1px solid #e0e0e0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="cid:logo_empresa" alt="Químicas Unidas">
                <h2 style="color: #475da4; margin: 10px 0 0 0;">Estado de Cuenta</h2>
            </div>

            <div class="content">
                <p>Estimado cliente: <span class="highlight">{nombre_cliente}</span></p>

                <p>Buenas tardes.<br>
                ¡Un gusto saludarle!</p>

                <p>Adjunto estado de cuenta para su revisión y cancelación de lo vencido mayor al plazo establecido de 30 días.</p>

                {resumen_html}

                <div class="policy-box">
                    <p style="margin-top: 0; font-weight: bold; color: #b8860b;">Favor tener presente estos puntos esenciales de nuestra política de crédito:</p>
                    <ul>
                        <li>El sistema de facturación tendrá una tolerancia adicional de <strong>1 semana</strong> después de vencidas las facturas antes de bloquear el despacho de mercancía.</li>
                        <li>El sistema de facturación condicionará su cuenta si la misma se encuentra al tope del límite de crédito otorgado por la compañía.</li>
                        <li>El sistema de facturación bloqueará su cuenta si la misma se encuentra con equipos en firme vencidos.</li>
                        <li>Facturas de equipos de bodega o demostración tienen <strong>plazo de 15 días</strong> y de no pagar en ese plazo se cobra interés moratorio.</li>
                        <li style="margin-bottom: 0;">Según indica la legislación y en la factura se girará documento de cobro de interés moratorio del 2.5% sobre las facturas y saldos vencidos por medio de una Nota de Débito que se le efectuará con <strong>plazo de 8 días</strong> al momento de la cancelación de lo vencido. El interés se cobra desde el primer día de vencida.</li>
                    </ul>
                </div>

                <p>Si ya realizó el pago por favor enviar comprobante para su revisión y aplicación.</p>
                
                <p>Si tiene dudas con su estado de cuenta por favor indicarlo para realizar una conciliación, de lo contrario se tomará como aceptado y de acuerdo.</p>

                <div class="contact-box">
                    <p style="margin: 0 0 15px 0; color: #333; font-size: 16px;"><strong>Correos para consultas o envío de comprobantes:</strong></p>
                    <div>
                        <a href="mailto:creditodenis@qu.cr" class="contact-email">creditodenis@qu.cr</a>
                        <span style="color: #475da4; font-size: 20px;">|</span>
                        <a href="mailto:credito@qu.cr" class="contact-email">credito@qu.cr</a>
                    </div>
                </div>

                <p style="margin-top: 30px;">Gracias.</p>

                <p>
                    Atentamente,<br><br>
                    <strong>HAZEL SOZA</strong><br>
                    <span style="color: #475da4; font-weight: bold;">QUIMICAS UNIDAS</span>
                </p>
            </div>

            <div class="footer">
                <p>Este es un correo automático generado por el sistema de gestión de cobros.</p>
                <p>© {datetime.now().year} Químicas Unidas S.A. - Todos los derechos reservados</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html


# =============================================================================
# CLASE PRINCIPAL - EMAIL SENDER
# =============================================================================

class EmailSenderCXC:
    """
    Clase para enviar correos usando Microsoft Graph API.
    """
    
    def __init__(self):
        self.token = None
        self.sender_email = SENDER_EMAIL
        
        if not MSAL_DISPONIBLE:
            raise ImportError("msal no está instalado. Ejecutar: pip install msal")
        
        if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
            raise ValueError("Faltan credenciales en .env: TENANT_ID, CLIENT_ID, CLIENT_SECRET")
    
    def get_access_token(self) -> str:
        """Obtiene token de acceso de Azure AD."""
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=authority
        )
        
        token_response = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        if "access_token" not in token_response:
            error = token_response.get('error_description', 'Error desconocido')
            raise Exception(f"Error obteniendo token: {error}")
        
        self.token = token_response["access_token"]
        return self.token
    
    def enviar_estado_cuenta(
        self,
        destinatarios: List[str],
        nombre_cliente: str,
        codigo_cliente: str,
        ruta_pdf: str,
        datos: Dict = None,
        cc_email: str = None
    ) -> bool:
        """
        Envía el estado de cuenta por correo.
        
        Args:
            destinatarios: Lista de correos destinatarios
            nombre_cliente: Nombre del cliente
            codigo_cliente: Código del cliente
            ruta_pdf: Ruta al archivo PDF
            datos: Datos del cliente (para personalización)
            cc_email: Correo en copia (opcional)
        
        Returns:
            True si se envió correctamente
        """
        # Validaciones
        if not destinatarios:
            print(f"   ❌ Sin destinatarios para {codigo_cliente}")
            return False
        
        if not os.path.exists(ruta_pdf):
            print(f"   ❌ PDF no encontrado: {ruta_pdf}")
            return False
        
        # Obtener token si no existe
        if not self.token:
            try:
                self.get_access_token()
            except Exception as e:
                print(f"   ❌ Error de autenticación: {e}")
                return False
        
        # Preparar destinatarios
        to_recipients = [
            {"emailAddress": {"address": email.strip()}} 
            for email in destinatarios
        ]
        
        # Generar HTML
        body_html = get_email_html(nombre_cliente, datos)
        
        # Construir mensaje
        message = {
            "subject": f"Químicas Unidas - Estado de Cuenta - {nombre_cliente}",
            "body": {
                "contentType": "HTML",
                "content": body_html
            },
            "toRecipients": to_recipients,
            "attachments": []
        }
        
        # Agregar CC si existe
        if cc_email:
            message["ccRecipients"] = [{"emailAddress": {"address": cc_email}}]
        
        # Adjuntar logo si existe
        if os.path.exists(RUTA_LOGO):
            try:
                with open(RUTA_LOGO, 'rb') as f:
                    logo_b64 = base64.b64encode(f.read()).decode('utf-8')
                message["attachments"].append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "logo.png",
                    "contentType": "image/png",
                    "contentBytes": logo_b64,
                    "contentId": "logo_empresa",
                    "isInline": True
                })
            except Exception as e:
                print(f"   ⚠️ Error adjuntando logo: {e}")
        
        # Adjuntar PDF
        try:
            with open(ruta_pdf, 'rb') as f:
                pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            pdf_filename = os.path.basename(ruta_pdf)
            message["attachments"].append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": pdf_filename,
                "contentType": "application/pdf",
                "contentBytes": pdf_b64
            })
        except Exception as e:
            print(f"   ❌ Error leyendo PDF: {e}")
            return False
        
        # Enviar correo
        email_msg = {
            "message": message,
            "saveToSentItems": "true"
        }
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json=email_msg)
            
            if response.status_code == 202:
                print(f"   ✅ Correo enviado a: {', '.join(destinatarios)}")
                return True
            else:
                print(f"   ❌ Error enviando: {response.status_code} - {response.text[:100]}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error de conexión: {e}")
            return False
    
    def enviar_control_interno(
        self,
        destinatarios: List[str],
        archivos: List[str]
    ) -> bool:
        """
        Envía correo de control interno con los archivos generados.
        
        Args:
            destinatarios: Lista de correos
            archivos: Lista de rutas a archivos adjuntos
        
        Returns:
            True si se envió correctamente
        """
        if not self.token:
            try:
                self.get_access_token()
            except Exception as e:
                print(f"❌ Error de autenticación: {e}")
                return False
        
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #475da4;">Control de Estados de Cuenta</h2>
            <p>Se adjuntan los documentos generados en la ejecución del proceso:</p>
            <ul>
                <li>Control de envíos de correos</li>
                <li>PDF unificado con estados de cuenta</li>
                <li>Excel con detalle</li>
            </ul>
            <p><strong>Fecha de ejecución:</strong> {fecha}</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Sistema de Automatización RPA - Químicas Unidas
            </p>
        </body>
        </html>
        """
        
        to_recipients = [
            {"emailAddress": {"address": email.strip()}} 
            for email in destinatarios
        ]
        
        message = {
            "subject": f"Control Estados de Cuenta - {datetime.now().strftime('%d/%m/%Y')}",
            "body": {
                "contentType": "HTML",
                "content": body_html
            },
            "toRecipients": to_recipients,
            "attachments": []
        }
        
        # Adjuntar archivos
        for ruta in archivos:
            if ruta and os.path.exists(ruta):
                try:
                    with open(ruta, 'rb') as f:
                        contenido_b64 = base64.b64encode(f.read()).decode('utf-8')
                    
                    ext = ruta.split('.')[-1].lower()
                    content_types = {
                        'pdf': 'application/pdf',
                        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        'xls': 'application/vnd.ms-excel',
                    }
                    
                    message["attachments"].append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": os.path.basename(ruta),
                        "contentType": content_types.get(ext, 'application/octet-stream'),
                        "contentBytes": contenido_b64
                    })
                except Exception as e:
                    print(f"⚠️ Error adjuntando {ruta}: {e}")
        
        email_msg = {
            "message": message,
            "saveToSentItems": "true"
        }
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json=email_msg)
            
            if response.status_code == 202:
                print(f"✅ Control enviado a: {', '.join(destinatarios)}")
                return True
            else:
                print(f"❌ Error enviando control: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error de conexión: {e}")
            return False


# =============================================================================
# FUNCIONES DE CONVENIENCIA
# =============================================================================

def enviar_estado_cuenta(
    destinatarios: List[str],
    nombre_cliente: str,
    codigo_cliente: str,
    ruta_pdf: str,
    datos: Dict = None
) -> bool:
    """
    Función de conveniencia para enviar estado de cuenta.
    Crea instancia de EmailSenderCXC y envía.
    """
    try:
        sender = EmailSenderCXC()
        return sender.enviar_estado_cuenta(
            destinatarios=destinatarios,
            nombre_cliente=nombre_cliente,
            codigo_cliente=codigo_cliente,
            ruta_pdf=ruta_pdf,
            datos=datos
        )
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


# =============================================================================
# PLANTILLA HTML PARA AGENTES
# =============================================================================

def get_agent_email_html(nombre_agente: str, fecha: str) -> str:
    """Genera el HTML para el correo que recibe el agente."""
    return f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #475da4; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">Reporte de Gira y Cobro</h2>
            </div>
            <div style="padding: 25px;">
                <p>Hola <strong>{nombre_agente}</strong>,</p>
                <p>Se adjunta el reporte consolidado de clientes con saldos pendientes para su gestión de cobro en campo.</p>
                <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #28a0cc;">
                    <p style="margin: 0;"><strong>Fecha de Generación:</strong> {fecha}</p>
                    <p style="margin: 5px 0 0 0;"><strong>Contenido:</strong> Detalle de facturas por cliente y zona.</p>
                </div>
                <p style="margin-top: 20px;">Por favor, utiliza este documento para coordinar las visitas y reportar cualquier gestión al departamento de Crédito.</p>
            </div>
            <div style="background-color: #f4f4f4; color: #777; padding: 15px; text-align: center; font-size: 12px;">
                Este es un envío automático del Sistema RPA - Químicas Unidas S.A.
            </div>
        </div>
    </body>
    </html>
    """

# =============================================================================
# CLASE PARA ENVÍO A AGENTES
# =============================================================================

class EmailSenderAgente(EmailSenderCXC):
    """
    Hereda de EmailSenderCXC para reutilizar la autenticación de Graph API,
    pero especializada en reportes de gira.
    """
    
    def enviar_reporte_gira(self, destinatario: str, nombre_agente: str, ruta_pdf: str) -> bool:
        """Envía el PDF consolidado al agente."""
        if not destinatario or "@" not in destinatario:
            print(f"   ⚠️ Agente {nombre_agente} sin correo válido. No se puede enviar.")
            return False

        if not self.token:
            self.get_access_token()

        fecha_str = datetime.now().strftime("%d/%m/%Y")
        body_html = get_agent_email_html(nombre_agente, fecha_str)

        message = {
            "subject": f"Reporte de Gira - Cobros - {nombre_agente} - {fecha_str}",
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": destinatario.strip()}}],
            "attachments": []
        }

        # Adjuntar PDF
        try:
            with open(ruta_pdf, 'rb') as f:
                import base64
                pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
                
            message["attachments"].append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": os.path.basename(ruta_pdf),
                "contentType": "application/pdf",
                "contentBytes": pdf_b64
            })
        except Exception as e:
            print(f"   ❌ Error adjuntando PDF al reporte: {e}")
            return False

        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        response = requests.post(url, headers=headers, json={"message": message})
        return response.status_code == 202

# Función de conveniencia (similar a la de CXC)
def enviar_email_agente(destinatario: str, nombre_agente: str, ruta_pdf: str) -> bool:
    try:
        sender = EmailSenderAgente()
        return sender.enviar_reporte_gira(destinatario, nombre_agente, ruta_pdf)
    except Exception as e:
        print(f"   ❌ Error en enviar_email_agente: {e}")
        return False