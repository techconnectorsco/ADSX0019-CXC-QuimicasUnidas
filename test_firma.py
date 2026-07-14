"""
test_firma.py - Prueba SOLO el tamaño de la firma en el correo.
No toca CXC ni SAP. Envía un correo de muestra a MI_CORREO.
"""

import os, base64, requests
from sendemailCXC import get_email_html, RUTA_LOGO, RUTA_FIRMA, EmailSenderCXC

# 👇 CAMBIÁ ESTO por tu correo donde querés recibir la prueba
MI_CORREO = "dev@soportexperto.com"


def enviar_prueba():
    sender = EmailSenderCXC()
    sender.get_access_token()

    # Correo de muestra con datos ficticios
    body_html = get_email_html("CLIENTE DE PRUEBA S.A.", datos=None, plazo_dias=30)

    message = {
        "subject": "PRUEBA - Tamaño de firma (NO es un estado de cuenta real)",
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [{"emailAddress": {"address": MI_CORREO}}],
        "attachments": [],
    }

    # Logo inline
    if os.path.exists(RUTA_LOGO):
        with open(RUTA_LOGO, "rb") as f:
            message["attachments"].append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "logo.png",
                    "contentType": "image/png",
                    "contentBytes": base64.b64encode(f.read()).decode("utf-8"),
                    "contentId": "logo_empresa",
                    "isInline": True,
                }
            )

    # Firma inline (la que estamos probando)
    if os.path.exists(RUTA_FIRMA):
        with open(RUTA_FIRMA, "rb") as f:
            message["attachments"].append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "firma.gif",
                    "contentType": "image/gif",
                    "contentBytes": base64.b64encode(f.read()).decode("utf-8"),
                    "contentId": "firma_asistente",
                    "isInline": True,
                }
            )
    else:
        print(f"⚠️ No se encontró la firma en {RUTA_FIRMA}")

    url = f"https://graph.microsoft.com/v1.0/users/{sender.sender_email}/sendMail"
    headers = {
        "Authorization": f"Bearer {sender.token}",
        "Content-Type": "application/json",
    }
    r = requests.post(
        url, headers=headers, json={"message": message, "saveToSentItems": "true"}
    )

    if r.status_code == 202:
        print(f"✅ Correo de prueba enviado a {MI_CORREO}. Revisá tu bandeja.")
    else:
        print(f"❌ Error {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    enviar_prueba()
