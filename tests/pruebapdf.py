import os
import sys
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.documentos.generarpdf_preliminar import PDF
from modules.comunicacion.sendemail import enviar_estado_cuenta
from config.settings import settings


def generar_y_enviar_prueba():
    ruta_logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "QU.png")
    ruta_salida = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prueba_estado_cuenta.pdf")

    cliente_info = {
        "id": "100254",
        "id_nombre": "100254 - INDUSTRIA DE ALIMENTOS S.A.",
        "telefono": "+506 2222-3333",
        "contacto": "Juan Pérez",
        "direccion": "San José, Costa Rica. Edificio Principal.",
        "email": "devs@techconnectors.co"
    }

    hoy = datetime.now()
    datos_facturas = {
        "DOCUMENTO": ["FAC-1001", "FAC-1002", "REC-500", "FAC-1005", "FAC-1008"],
        "FECHA_FACTURA": [
            (hoy - timedelta(days=45)).strftime("%Y-%m-%d"),
            (hoy - timedelta(days=20)).strftime("%Y-%m-%d"),
            (hoy - timedelta(days=15)).strftime("%Y-%m-%d"),
            (hoy - timedelta(days=5)).strftime("%Y-%m-%d"),
            hoy.strftime("%Y-%m-%d")
        ],
        "FECHA_VENCE": [
            (hoy - timedelta(days=15)).strftime("%Y-%m-%d"),
            (hoy + timedelta(days=10)).strftime("%Y-%m-%d"),
            (hoy - timedelta(days=15)).strftime("%Y-%m-%d"),
            (hoy + timedelta(days=25)).strftime("%Y-%m-%d"),
            (hoy + timedelta(days=30)).strftime("%Y-%m-%d")
        ],
        "MONTO_FACTURA": [1500.50, 3200.00, 1500.50, 850.75, 4100.00],
        "SALDO_FACTURA": [1500.50, 3200.00, 1500.50, 850.75, 4100.00],
        "MONEDA": ["USD", "CRC", "USD", "USD", "CRC"],
        "TIPO": ["FAC", "FAC", "REC", "FAC", "FAC"]
    }

    df = pd.DataFrame(datos_facturas)

    print("Generando PDF...")
    pdf = PDF(logo_path=ruta_logo)
    pdf.alias_nb_pages()

    info_qr = (
        f"CLIENTE: {cliente_info['id_nombre']}\n"
        f"CONTACTO: {cliente_info['contacto']}\n"
        f"TEL: {cliente_info['telefono']}\n"
        f"EMAIL: {cliente_info['email']}\n"
        f"GENERADO: {hoy.strftime('%Y-%m-%d %H:%M')}"
    )
    pdf.qr_data = info_qr

    pdf.add_page()
    pdf.chapter_title(
        cliente_id_nombre=cliente_info["id_nombre"],
        telefono=cliente_info["telefono"],
        contacto=cliente_info["contacto"],
        direccion=cliente_info["direccion"],
        email=cliente_info["email"]
    )

    lista_datos = df.values.tolist()
    saldo, docs = pdf.add_table(lista_datos)

    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
    pdf.output(ruta_salida)
    print(f"✅ PDF generado: {ruta_salida}")

    # Requiere SMTP_USER y SMTP_PASS configurados en .env como EMAIL_SENDER / EMAIL_PASSWORD
    smtp_user = settings.EMAIL_SENDER
    smtp_pass = os.getenv("EMAIL_PASSWORD", "")

    print("Iniciando envío de correo...")
    exito = enviar_estado_cuenta(
        cliente_id=cliente_info["id"],
        nombre_cliente=cliente_info["id_nombre"],
        email_cliente=cliente_info["email"],
        ruta_pdf=ruta_salida,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        ruta_logo=ruta_logo
    )

    if exito:
        print("✅ Proceso completado exitosamente.")
    else:
        print("❌ Hubo un problema al enviar el correo.")


if __name__ == "__main__":
    generar_y_enviar_prueba()
