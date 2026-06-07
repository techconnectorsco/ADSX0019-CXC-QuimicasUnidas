from datetime import datetime

status_global_ejecution = {
    "fecha_ejecucion": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    "tiempo_ejecucion": None,
    # Embudo de clientes
    "total_clientes": 0,  # clientes con saldo devueltos por SAP
    "clientes_procesados": 0,  # con documentos pendientes (gestionados)
    "clientes_omitidos_N": 0,  # envío automático deshabilitado
    "clientes_sin_documentos": 0,  # saldo en SAP pero sin docs abiertos
    "clientes_sin_correo": 0,  # con docs pero sin correo configurado
    # Documentos / reportes
    "total_documentos_procesados": 0,
    "reportes_generados": 0,  # PDFs individuales generados
    # Correos (Microsoft Graph)
    "emails_exitosos": 0,
    "emails_fallidos": 0,
    # Montos (cartera gestionada)
    "monto_total_usd": 0.00,
    "monto_total_colones": 0.00,
    "monto_vencido_usd": 0.00,
    "monto_vencido_colones": 0.00,
    "tipo_ejecucion": "Automatica",
    "fuente": "Quimicas-Unidas-CxC",
}
