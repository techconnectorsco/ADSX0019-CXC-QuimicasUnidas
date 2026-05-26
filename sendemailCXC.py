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
# CONFIGURACIÓN Y CONSTANTES BANCARIAS
# =============================================================================

if DECOUPLE_DISPONIBLE:
    TENANT_ID = config("TENANT_ID", default="")
    CLIENT_ID = config("CLIENT_ID", default="")
    CLIENT_SECRET = config("CLIENT_SECRET", default="")
    SENDER_EMAIL = config("SENDER_EMAIL", default="boot@soportexperto.com")
else:
    TENANT_ID = os.environ.get("TENANT_ID", "")
    CLIENT_ID = os.environ.get("CLIENT_ID", "")
    CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "boot@soportexperto.com")

# Rutas de imágenes
RUTA_LOGO = "images/QU.png"
RUTA_FIRMA = "images/Firma_digital_Asistente.gif"

# Cuentas bancarias para el cuerpo del correo
CUENTAS_BANCARIAS = [
    {
        "banco": "BCR",
        "moneda": "COLONES",
        "cuenta": "001-145244-4",
        "cc": "15201001014524442",
        "iban": "CR36015201001014524442",
    },
    {
        "banco": "BCR",
        "moneda": "DÓLARES",
        "cuenta": "001-0279168-4",
        "cc": None,
        "iban": "CR52015201001027916847",
    },
    {
        "banco": "BN",
        "moneda": "COLONES",
        "cuenta": "100-01-000-016985-4",
        "cc": "15100010010169851",
        "iban": "CR50015100010010169851",
    },
    {
        "banco": "BAC SAN JOSÉ",
        "moneda": "COLONES",
        "cuenta": None,
        "cc": None,
        "iban": "CR60010200009019709051",
    },
]

# =============================================================================
# GENERACIÓN DE HTML
# =============================================================================


def generar_html_cuentas() -> str:
    """Genera una sección HTML estilizada para las cuentas bancarias."""
    cuentas_colones = [c for c in CUENTAS_BANCARIAS if c["moneda"] == "COLONES"]
    cuentas_dolares = [c for c in CUENTAS_BANCARIAS if c["moneda"] == "DÓLARES"]

    html = """
    <div style="background-color: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; margin: 25px 0; overflow: hidden;">
        <div style="background-color: #475da4; color: white; padding: 12px 20px; font-weight: bold; font-size: 16px;">
            🏦 Cuentas Bancarias Autorizadas
        </div>
        <div style="padding: 20px;">
            <p style="margin-top: 0; color: #666; font-size: 14px;">Para facilitar sus pagos, adjuntamos nuestras cuentas bancarias. Si escanea el código QR en su PDF adjunto, también podrá acceder a esta información.</p>
    """

    # Render Colones
    html += f"""
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <tr style="background-color: #e3f2fd;"><th colspan="4" style="padding: 8px; text-align: left; color: #0066cc; border-bottom: 2px solid #90caf9;">Cuentas en COLONES (₡)</th></tr>
            <tr style="font-size: 13px; color: #555; background-color: #f1f1f1;">
                <th style="padding: 8px; text-align: left;">Banco</th>
                <th style="padding: 8px; text-align: left;">Cuenta Corriente</th>
                <th style="padding: 8px; text-align: left;">Cuenta Cliente (CC)</th>
                <th style="padding: 8px; text-align: left;">Cuenta IBAN</th>
            </tr>
    """
    for c in cuentas_colones:
        cta = c["cuenta"] or "N/A"
        cc = c["cc"] or "N/A"
        html += f"""
            <tr style="font-size: 13px; border-bottom: 1px solid #eee;">
                <td style="padding: 8px; font-weight: bold;">{c['banco']}</td>
                <td style="padding: 8px;">{cta}</td>
                <td style="padding: 8px;">{cc}</td>
                <td style="padding: 8px; font-family: monospace;">{c['iban']}</td>
            </tr>
        """
    html += "</table>"

    # Render Dólares
    html += f"""
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background-color: #e8f5e9;"><th colspan="4" style="padding: 8px; text-align: left; color: #2e7d32; border-bottom: 2px solid #a5d6a7;">Cuentas en DÓLARES ($)</th></tr>
            <tr style="font-size: 13px; color: #555; background-color: #f1f1f1;">
                <th style="padding: 8px; text-align: left;">Banco</th>
                <th style="padding: 8px; text-align: left;">Cuenta Corriente</th>
                <th style="padding: 8px; text-align: left;">Cuenta Cliente (CC)</th>
                <th style="padding: 8px; text-align: left;">Cuenta IBAN</th>
            </tr>
    """
    for c in cuentas_dolares:
        cta = c["cuenta"] or "N/A"
        cc = c["cc"] or "N/A"
        html += f"""
            <tr style="font-size: 13px; border-bottom: 1px solid #eee;">
                <td style="padding: 8px; font-weight: bold;">{c['banco']}</td>
                <td style="padding: 8px;">{cta}</td>
                <td style="padding: 8px;">{cc}</td>
                <td style="padding: 8px; font-family: monospace;">{c['iban']}</td>
            </tr>
        """
    html += """
        </table>
        </div>
    </div>
    """
    return html


def get_email_html(
    nombre_cliente: str, datos: Dict = None, plazo_dias: int = 30
) -> str:
    resumen_html = ""
    if datos:
        totales = datos.get("totales", {})
        if totales.get("dolares", 0) != 0 or totales.get("colones", 0) != 0:
            resumen_html = """
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 0; font-weight: bold; color: #0066cc; font-size: 16px;">Resumen de su cuenta:</p>
            """
            if totales.get("dolares", 0) != 0:
                resumen_html += f'<p style="margin: 5px 0; font-size: 15px;">• Saldo en Dólares: <strong>USD {totales["dolares"]:,.2f}</strong></p>'
            if totales.get("colones", 0) != 0:
                resumen_html += f'<p style="margin: 5px 0; font-size: 15px;">• Saldo en Colones: <strong>CRC {totales["colones"]:,.2f}</strong></p>'
            resumen_html += "</div>"

    cuentas_bancarias_html = generar_html_cuentas()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #333333; background-color: #f4f4f4; margin: 0; padding: 0; line-height: 1.6; }}
            .container {{ max-width: 900px; margin: 30px auto; background-color: #ffffff; padding: 40px 50px; border-radius: 10px; box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.1); }}
            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 3px solid #28a0cc; margin-bottom: 25px; }}
            .header img {{ max-width: 200px; height: auto; }}
            .content {{ font-size: 15px; }}
            .highlight {{ color: #0066cc; font-weight: bold; font-size: 16px; }}
            .policy-box {{ background-color: #fdfaf0; border-left: 4px solid #f0ad4e; padding: 20px 25px; margin: 25px 0; border-radius: 0 8px 8px 0; }}
            .policy-box ul {{ margin: 0; padding-left: 20px; }}
            .policy-box li {{ margin-bottom: 12px; font-size: 14px; }}
            .contact-box {{ background-color: #e3f2fd; padding: 25px; border-radius: 8px; margin-top: 30px; text-align: center; border: 1px solid #bbdefb; }}
            .contact-email {{ font-size: 20px; font-weight: bold; color: #475da4; margin: 8px 15px; display: inline-block; text-decoration: none; }}
            .footer {{ text-align: center; font-size: 12px; color: #666666; margin-top: 35px; padding-top: 20px; border-top: 1px solid #e0e0e0; }}
            .firma-img {{ max-width: 350px; height: auto; margin-top: 15px; display: block; }}
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

                <p>Adjunto estado de cuenta para su revisión y cancelación de lo vencido mayor al plazo establecido de {plazo_dias} días.</p>

                {resumen_html}
                
                {cuentas_bancarias_html}

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

                <div>
                    Atentamente,<br>
                    <img src="cid:firma_asistente" alt="Asistente Digital - Químicas Unidas" class="firma-img">
                </div>
            </div>

            <div class="footer">
                <p>Este es un correo automático generado por el sistema de gestión de cobros.</p>
                <p>© {datetime.now().year} Químicas Unidas Ltda. - Todos los derechos reservados</p>
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
    def __init__(self):
        self.token = None
        self.sender_email = SENDER_EMAIL

        if not MSAL_DISPONIBLE:
            raise ImportError("msal no está instalado. Ejecutar: pip install msal")

        if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
            raise ValueError(
                "Faltan credenciales en .env: TENANT_ID, CLIENT_ID, CLIENT_SECRET"
            )

    def get_access_token(self) -> str:
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID, client_credential=CLIENT_SECRET, authority=authority
        )
        token_response = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in token_response:
            error = token_response.get("error_description", "Error desconocido")
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
        cc_email: str = None,
        plazo_dias: int = 30,
        ruta_excel: str = None,
    ) -> bool:

        if not destinatarios:
            return False
        if not os.path.exists(ruta_pdf):
            return False
        if not self.token:
            try:
                self.get_access_token()
            except:
                return False

        to_recipients = [
            {"emailAddress": {"address": email.strip()}} for email in destinatarios
        ]
        body_html = get_email_html(nombre_cliente, datos, plazo_dias)

        message = {
            "subject": f"Químicas Unidas - Estado de Cuenta - {nombre_cliente}",
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": to_recipients,
            "attachments": [],
        }

        if cc_email:
            message["ccRecipients"] = [{"emailAddress": {"address": cc_email}}]

        # 1. Adjuntar Logo
        if os.path.exists(RUTA_LOGO):
            try:
                with open(RUTA_LOGO, "rb") as f:
                    logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                message["attachments"].append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": "logo.png",
                        "contentType": "image/png",
                        "contentBytes": logo_b64,
                        "contentId": "logo_empresa",
                        "isInline": True,
                    }
                )
            except Exception as e:
                print(f"   ⚠️ Error adjuntando logo: {e}")

        # 2. Adjuntar Firma GIF Animada
        if os.path.exists(RUTA_FIRMA):
            try:
                with open(RUTA_FIRMA, "rb") as f:
                    firma_b64 = base64.b64encode(f.read()).decode("utf-8")
                message["attachments"].append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": "firma.gif",
                        "contentType": "image/gif",
                        "contentBytes": firma_b64,
                        "contentId": "firma_asistente",
                        "isInline": True,
                    }
                )
            except Exception as e:
                print(f"   ⚠️ Error adjuntando firma: {e}")

        # 3. Adjuntar PDF
        try:
            with open(ruta_pdf, "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
            message["attachments"].append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": os.path.basename(ruta_pdf),
                    "contentType": "application/pdf",
                    "contentBytes": pdf_b64,
                }
            )
        except:
            return False

        # 4. Adjuntar Excel
        if ruta_excel and os.path.exists(ruta_excel):
            try:
                with open(ruta_excel, "rb") as f:
                    excel_b64 = base64.b64encode(f.read()).decode("utf-8")
                message["attachments"].append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": os.path.basename(ruta_excel),
                        "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "contentBytes": excel_b64,
                    }
                )
            except:
                pass

        email_msg = {"message": message, "saveToSentItems": "true"}
        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, headers=headers, json=email_msg)
            return response.status_code == 202
        except:
            return False

    def enviar_control_interno(
        self, destinatarios: List[str], archivos: List[str], stats: Dict = None
    ) -> bool:
        if not self.token:
            try:
                self.get_access_token()
            except:
                return False

        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime("%I:%M %p")

        stats_html = ""
        if stats:
            stats_html = f"""
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #475da4;">
                    <p style="margin: 0 0 10px 0; font-weight: bold; color: #475da4;">Resumen de Ejecucion:</p>
                    <table style="width: 100%;">
                        <tr><td>Clientes procesados:</td><td><strong>{stats.get('procesados', 0)}</strong></td></tr>
                        <tr><td style="color: #28a745;">Correos enviados:</td><td style="color: #28a745;"><strong>{stats.get('enviados', 0)}</strong></td></tr>
                        <tr><td style="color: #ffc107;">Sin correo:</td><td style="color: #ffc107;"><strong>{stats.get('sin_correo', 0)}</strong></td></tr>
                        <tr><td style="color: #dc3545;">Errores:</td><td style="color: #dc3545;"><strong>{stats.get('errores', 0)}</strong></td></tr>
                    </table>
                </div>
                """

        body_html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: 'Segoe UI', Arial, sans-serif; color: #333; background-color: #f4f4f4; margin: 0; padding: 0;">
                <div style="max-width: 700px; margin: 20px auto; background-color: #fff; padding: 30px; border-radius: 10px;">
                    <div style="text-align: center; padding-bottom: 20px; border-bottom: 3px solid #28a0cc; margin-bottom: 25px;">
                        <h1 style="color: #475da4; margin: 0;">Quimicas Unidas Ltda.</h1>
                        <h2 style="color: #666; font-weight: normal; margin: 5px 0 0 0;">Log de Control - Estados de Cuenta</h2>
                    </div>
                    <p>Se ha completado la ejecucion del proceso de Estados de Cuenta.</p>
                    <p><strong>Fecha:</strong> {fecha} a las {hora}</p>
                    {stats_html}
                    <p>Se adjunta el documento PDF con el detalle completo.</p>
                </div>
            </body>
            </html>
            """
        to_recipients = [
            {"emailAddress": {"address": email.strip()}} for email in destinatarios
        ]
        message = {
            "subject": f"Control Estados de Cuenta - {datetime.now().strftime('%d/%m/%Y')}",
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": to_recipients,
            "attachments": [],
        }

        for ruta in archivos:
            if ruta and os.path.exists(ruta):
                try:
                    with open(ruta, "rb") as f:
                        cont_b64 = base64.b64encode(f.read()).decode("utf-8")
                    ext = ruta.split(".")[-1].lower()
                    ctypes = {
                        "pdf": "application/pdf",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "xls": "application/vnd.ms-excel",
                    }
                    message["attachments"].append(
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": os.path.basename(ruta),
                            "contentType": ctypes.get(ext, "application/octet-stream"),
                            "contentBytes": cont_b64,
                        }
                    )
                except:
                    pass

        email_msg = {"message": message, "saveToSentItems": "true"}
        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=email_msg)
            return response.status_code == 202
        except:
            return False


# =============================================================================
# FUNCIONES DE CONVENIENCIA
# =============================================================================


def enviar_estado_cuenta(
    destinatarios: List[str],
    nombre_cliente: str,
    codigo_cliente: str,
    ruta_pdf: str,
    datos: Dict = None,
    plazo_dias: int = 30,
    ruta_excel: str = None,
) -> bool:
    try:
        sender = EmailSenderCXC()
        return sender.enviar_estado_cuenta(
            destinatarios,
            nombre_cliente,
            codigo_cliente,
            ruta_pdf,
            datos,
            plazo_dias=plazo_dias,
            ruta_excel=ruta_excel,
        )
    except:
        return False


def get_agent_email_html(nombre_agente: str, fecha: str) -> str:
    return f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #475da4; color: white; padding: 20px; text-align: center;"><h2 style="margin: 0;">Reporte de Gira y Cobro</h2></div>
            <div style="padding: 25px;">
                <p>Hola <strong>{nombre_agente}</strong>,</p>
                <p>Se adjunta el reporte consolidado de clientes con saldos pendientes para su gestión de cobro en campo.</p>
                <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #28a0cc;">
                    <p style="margin: 0;"><strong>Fecha de Generación:</strong> {fecha}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


class EmailSenderAgente(EmailSenderCXC):
    def enviar_reporte_gira(
        self, destinatario: str, nombre_agente: str, ruta_pdf: str, cc: List[str] = None
    ) -> bool:
        if not destinatario or "@" not in destinatario:
            return False
        if not self.token:
            self.get_access_token()
        fecha_str = datetime.now().strftime("%d/%m/%Y")
        body_html = get_agent_email_html(nombre_agente, fecha_str)
        message = {
            "subject": f"Reporte de Gira - Cobros - {nombre_agente} - {fecha_str}",
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": destinatario.strip()}}],
            "attachments": [],
        }
        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": email.strip()}} for email in cc
            ]
        try:
            with open(ruta_pdf, "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
            message["attachments"].append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": os.path.basename(ruta_pdf),
                    "contentType": "application/pdf",
                    "contentBytes": pdf_b64,
                }
            )
        except:
            return False
        url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, headers=headers, json={"message": message})
        return response.status_code == 202


def enviar_email_agente(
    destinatario: str, nombre_agente: str, ruta_pdf: str, cc: List[str] = None
) -> bool:
    try:
        return EmailSenderAgente().enviar_reporte_gira(
            destinatario, nombre_agente, ruta_pdf, cc
        )
    except:
        return False
