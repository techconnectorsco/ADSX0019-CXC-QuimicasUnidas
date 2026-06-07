from datetime import datetime

status_global_giras = {
    "fecha_ejecucion": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    "tiempo_ejecucion": None,
    # Clientes / agentes
    "total_clientes": 0,  # clientes extraídos de SAP
    "clientes_evaluados": 0,  # clientes analizados (multihilo)
    "total_agentes": 0,  # agentes activos con cartera (correo + docs)
    "agentes_procesados": 0,  # agentes con reporte generado
    # Reportes / documentos
    "reportes_generados": 0,  # PDFs de gira generados
    "total_documentos_procesados": 0,
    # Correos
    "emails_exitosos": 0,
    "emails_fallidos": 0,
    # Montos
    "monto_total_usd": 0.00,
    "monto_total_colones": 0.00,
    "monto_vencido_usd": 0.00,
    "monto_vencido_colones": 0.00,
    "tipo_ejecucion": "Automatica",
    "fuente": "Quimicas-Unidas-Giras",
}
