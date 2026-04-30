#!/usr/bin/env python3
"""
test_teams.py - Prueba del módulo de comunicación Teams
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.comunicacion import TeamsNotifier


def print_result(result: dict):
    if result['success']:
        print("✅ Mensaje enviado correctamente")
    else:
        print(f"❌ Error: {result.get('error', 'Desconocido')}")


def main():
    print("\n" + "=" * 50)
    print("🤖 Test de Teams - Químicas Unidas")
    print("=" * 50)

    try:
        notifier = TeamsNotifier()
    except ValueError as e:
        print(f"❌ {e}")
        return

    print("\n1. Mensaje simple")
    result = notifier.send_simple(
        "🔔 Prueba de conexión desde el Asistente Digital de Químicas Unidas."
    )
    print_result(result)

    print("\n2. Reporte de ejecución")
    result = notifier.send_execution_report(
        process_name="Estados de Cuenta CXC (PRUEBA)",
        success=True,
        start_time=datetime.now() - timedelta(minutes=3),
        records_processed=185,
        records_success=180,
        records_failed=5
    )
    print_result(result)

    print("\n3. Resumen CXC")
    result = notifier.send_cxc_summary(
        total_clientes=195,
        enviados=180,
        excluidos=10,
        errores=5,
        monto_total_crc=45_678_900.50,
        monto_total_usd=12_345.67
    )
    print_result(result)

    print("\n4. Resumen Giras")
    result = notifier.send_agent_report_summary(
        total_agentes=8,
        reportes_enviados=8,
        total_clientes_gira=156
    )
    print_result(result)

    print("\n5. Alerta de error")
    result = notifier.send_error_alert(
        process_name="Envío Estados de Cuenta (PRUEBA)",
        error_message="Este es un error de prueba",
        error_details="Detalles técnicos del error simulado"
    )
    print_result(result)

    print("\n" + "=" * 50)
    print("✅ Pruebas completadas - Revisa el canal de Teams")
    print("=" * 50)


if __name__ == "__main__":
    main()
