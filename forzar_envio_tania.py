"""
forzar_envio_tania.py - Químicas Unidas
Versión definitiva: Pasa la lista de clientes como parámetro directo a la función.
"""

import sys
import os
import argparse

# Forzar el path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. Importamos main e interceptamos la configuración global
import main

CORREO_TANIA = "credito@qu.cr"
main.MODO_PRUEBA = True
main.EMAIL_PRUEBA = CORREO_TANIA

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envío forzado exclusivo a Tania.")
    parser.add_argument("--clientes", type=str, required=True, help="Ej: C0161,C0040")
    args = parser.parse_args()

    # 2. Convertimos el texto "C0161,C0040" en una lista real de Python ['C0161', 'C0040']
    lista_codigos = args.clientes.split(",")

    print("=" * 80)
    print("🚀 PROCESO INTERNO: FORZAR ENVÍO EXCLUSIVO A TANIA")
    print(f"🎯 Destinatario: {CORREO_TANIA}")
    print(f"👥 Clientes a procesar: {lista_codigos}")
    print("=" * 80)

    # 3. Le pasamos la lista DIRECTAMENTE a la función (esto evita que traiga a todos)
    main.ejecutar_proceso_cxc(lista_clientes=lista_codigos)
