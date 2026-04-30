"""
Módulo sendemail.py - Químicas Unidas
Envío de correos electrónicos con estados de cuenta.
Adaptado del proyecto Vedova y Obando.
"""

import os
import smtplib
from email.message import EmailMessage
from datetime import datetime


SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587


def get_email_html(nombre_cliente: str) -> str:
    """
    Genera el HTML del correo de estado de cuenta.

    Args:
        nombre_cliente: Nombre del cliente destinatario

    Returns:
        String con el HTML del correo
    """
    # TODO: Actualizar cuentas bancarias reales de Químicas Unidas
    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                color: #333333;
                background-color: #f4f4f4;
                margin: 0;
                padding: 0;
            }}
            .container {{
                width: 80%;
                margin: 20px auto;
                background-color: #ffffff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 10px;
            }}
            .header img {{
                width: 250px;
                height: auto;
            }}
            .content {{
                font-size: 14px;
                line-height: 1.5;
            }}
            .footer {{
                text-align: center;
                font-size: 12px;
                color: #666666;
                margin-top: 10px;
                padding-top: 10px;
                border-top: 1px solid #e0e0e0;
            }}
            .highlight {{
                color: #0066cc;
                font-weight: bold;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                font-size: 13px;
                text-align: center;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 6px;
            }}
            th {{
                background-color: #f0f0f0;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="cid:logo_empresa" alt="Quimicas Unidas Logo">
            </div>

            <div class="content">
                <p><strong>NOTA: El estado de cuenta es informativo. Si no tiene ninguna factura vencida, omita este correo. NO CONTESTAR A ESTE CORREO.</strong></p>

                <p>Estimado cliente: <span class="highlight">{nombre_cliente}</span></p>

                <p>Un gusto saludarle.</p>

                <p>Adjunto al final de este correo encontrara el estado de cuenta de su representada. Solicitamos cordialmente verificar la informacion suministrada e indicar si ya se encuentra conciliada o bien confirmar la fecha de pago de las facturas vencidas.</p>

                <p>Si ya cancelo o realizo algun abono, remita el comprobante de pago al correo <strong>cxc@quimicasunidas.com</strong> para su debida aplicacion.</p>

                <p><strong>Le detallamos las cuentas bancarias para su respectivo deposito o transferencia:</strong></p>

                <table>
                    <thead>
                        <tr>
                            <th>Entidad</th>
                            <th>Moneda</th>
                            <th>Cuenta</th>
                            <th>IBAN</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- TODO: Agregar cuentas bancarias reales -->
                        <tr>
                            <td><strong>BCR</strong></td>
                            <td>CRC</td>
                            <td>000-00-000000-0</td>
                            <td>CR00000000000000000000</td>
                        </tr>
                        <tr>
                            <td><strong>BN</strong></td>
                            <td>CRC</td>
                            <td>000-00-000-000000-0</td>
                            <td>CR00000000000000000000</td>
                        </tr>
                        <tr>
                            <td><strong>BN</strong></td>
                            <td>USD</td>
                            <td>000-00-000-000000</td>
                            <td>CR00000000000000000000</td>
                        </tr>
                        <tr>
                            <td><strong>BAC</strong></td>
                            <td>CRC</td>
                            <td>000000000</td>
                            <td>CR00000000000000000000</td>
                        </tr>
                        <tr>
                            <td><strong>BAC</strong></td>
                            <td>USD</td>
                            <td>000000000</td>
                            <td>CR00000000000000000000</td>
                        </tr>
                    </tbody>
                </table>

                <p style="text-align: center; margin-top: 15px;">
                    <strong>SINPE Movil al numero <span class="highlight">0000-0000</span></strong>
                </p>

                <p>Saludos Cordiales;</p>

                <p>
                    Cuentas por Cobrar<br>
                    0000-0000 Ext 000<br>
                    Reportar los pagos al correo <strong>cxc@quimicasunidas.com</strong> o al WhatsApp <a href="https://wa.me/50600000000" style="color: #25D366; font-weight: bold;">+506 0000-0000</a>.
                </p>
            </div>

            <div class="footer">
                <hr>
                <img src="cid:footer_empresa" alt="Pie de Pagina">
                <hr>
            </div>
        </div>
    </body>
    </html>
    """
    return html


def enviar_estado_cuenta(
    cliente_id: str,
    nombre_cliente: str,
    email_cliente: str,
    ruta_pdf: str,
    smtp_user: str,
    smtp_pass: str,
    ruta_logo: str = None,
    ruta_footer: str = None,
    log_pdf=None
) -> bool:
    """
    Envía el estado de cuenta por correo electrónico.

    Args:
        cliente_id: Código del cliente
        nombre_cliente: Nombre del cliente
        email_cliente: Email del destinatario
        ruta_pdf: Ruta al archivo PDF adjunto
        smtp_user: Usuario SMTP
        smtp_pass: Contraseña SMTP
        ruta_logo: Ruta al logo (opcional)
        ruta_footer: Ruta a imagen footer (opcional)
        log_pdf: Instancia de LogPDF para registrar el envío (opcional)

    Returns:
        True si se envió correctamente, False si hubo error
    """
    nombre_codigo = f"{nombre_cliente} - {cliente_id}"

    # Validar email
    if not email_cliente or "@" not in str(email_cliente):
        print(f"❌ Cliente {cliente_id} - {nombre_cliente} no tiene correo valido. Se omite.")
        if log_pdf:
            log_pdf.add_log_entry(nombre_codigo, "SIN CORREO", "No", "No tiene email")
        return False

    # Validar PDF
    if not os.path.exists(ruta_pdf):
        print(f"⚠️ PDF no encontrado para {cliente_id}")
        if log_pdf:
            log_pdf.add_log_entry(nombre_codigo, email_cliente, "No", "PDF no encontrado")
        return False

    body = get_email_html(nombre_cliente)

    msg = EmailMessage()
    msg['Subject'] = f"Quimicas Unidas - Estado de Cuenta - {nombre_cliente}"
    msg['From'] = f"Quimicas Unidas CxC<{smtp_user}>"
    msg['To'] = email_cliente
    msg.set_content(body, subtype='html')

    # Adjuntar logo si existe
    if ruta_logo and os.path.exists(ruta_logo):
        try:
            with open(ruta_logo, 'rb') as img_file:
                ext = ruta_logo.split('.')[-1].lower()
                subtype = 'jpeg' if ext in ['jpg', 'jpeg'] else ext
                msg.add_attachment(
                    img_file.read(),
                    maintype='image',
                    subtype=subtype,
                    filename=os.path.basename(ruta_logo),
                    cid="logo_empresa"
                )
        except Exception as e:
            print(f"Error adjuntando logo: {e}")

    # Adjuntar footer si existe
    if ruta_footer and os.path.exists(ruta_footer):
        try:
            with open(ruta_footer, 'rb') as img_file:
                ext = ruta_footer.split('.')[-1].lower()
                subtype = 'jpeg' if ext in ['jpg', 'jpeg'] else ext
                msg.add_attachment(
                    img_file.read(),
                    maintype='image',
                    subtype=subtype,
                    filename=os.path.basename(ruta_footer),
                    cid="footer_empresa"
                )
        except Exception as e:
            print(f"Error adjuntando footer: {e}")

    # Adjuntar PDF
    try:
        with open(ruta_pdf, 'rb') as f:
            msg.add_attachment(
                f.read(),
                maintype='application',
                subtype='pdf',
                filename=os.path.basename(ruta_pdf)
            )
    except Exception as e:
        print(f"❌ Error adjuntando PDF: {e}")
        if log_pdf:
            log_pdf.add_log_entry(nombre_codigo, email_cliente, "No", "Error adjuntando PDF")
        return False

    # Enviar correo
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        print(f"✅ Correo enviado a {email_cliente}")
        if log_pdf:
            log_pdf.add_log_entry(nombre_codigo, email_cliente, "Si")
        return True
    except Exception as e:
        print(f"❌ Error al enviar: {e}")
        if log_pdf:
            log_pdf.add_log_entry(nombre_codigo, email_cliente, "No", str(e)[:40])
        return False


def enviar_control_interno(
    destinatarios: list,
    ruta_log_pdf: str,
    ruta_pdf_unificado: str,
    ruta_excel: str,
    smtp_user: str,
    smtp_pass: str
) -> bool:
    """
    Envía correo de control interno con los archivos generados.

    Args:
        destinatarios: Lista de emails
        ruta_log_pdf: Ruta al PDF de log de envíos
        ruta_pdf_unificado: Ruta al PDF unificado
        ruta_excel: Ruta al Excel con detalle
        smtp_user: Usuario SMTP
        smtp_pass: Contraseña SMTP

    Returns:
        True si se envió correctamente
    """
    subject = "Control y Estados de Cuenta Unificados - Quimicas Unidas"
    body = f"""
    Estimado equipo,

    Se adjuntan los siguientes documentos:
    - Control de envios de correos electronicos.
    - PDF unificado con los estados de cuenta generados.
    - Excel con el detalle de todos los estados de cuenta.

    Fecha de ejecucion: {datetime.now().strftime("%d/%m/%Y %H:%M")}

    Saludos,
    Sistema de Automatizacion RPA
    """

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"Quimicas Unidas Control CxC<{smtp_user}>"
    msg['To'] = ', '.join(destinatarios)
    msg.set_content(body)

    archivos = [
        (ruta_log_pdf, 'pdf'),
        (ruta_pdf_unificado, 'pdf'),
        (ruta_excel, 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    ]

    for ruta, subtype in archivos:
        if ruta and os.path.exists(ruta):
            try:
                with open(ruta, 'rb') as f:
                    msg.add_attachment(
                        f.read(),
                        maintype='application',
                        subtype=subtype,
                        filename=os.path.basename(ruta)
                    )
            except Exception as e:
                print(f"❌ Error adjuntando {ruta}: {e}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        print(f"✅ Control enviado a: {', '.join(destinatarios)}")
        return True
    except Exception as e:
        print(f"❌ Error enviando control: {e}")
        return False
