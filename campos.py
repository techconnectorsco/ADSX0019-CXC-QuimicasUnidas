"""
investigar_campos.py - Químicas Unidas
Script para investigar qué campos contienen descuentos en BusinessPartners de SAP.

Uso:
    python investigar_campos.py

Esto mostrará:
1. Un cliente con todos sus campos disponibles
2. Campos que mencionan "discount" o "descuento"
3. Valores reales para análisis
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection


def investigar_campos_cliente():
    print("=" * 80)
    print("🔍 INVESTIGACIÓN: Campos de Descuento en BusinessPartners")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        # Obtener un cliente con todos los campos
        print("\n📋 Obteniendo datos de UN cliente para análisis...")
        resultado = conn.get(
            "BusinessPartners",
            {"$filter": "CardType eq 'cCustomer' and Valid eq 'tYES'", "$top": 1},
        )

        if not resultado or "value" not in resultado or len(resultado["value"]) == 0:
            print("❌ No hay clientes disponibles")
            return

        cliente = resultado["value"][0]
        codigo_cliente = cliente.get("CardCode", "DESCONOCIDO")
        nombre_cliente = cliente.get("CardName", "DESCONOCIDO")

        print(f"\n✅ Cliente seleccionado: {codigo_cliente} - {nombre_cliente}")

        # Listar TODOS los campos
        print("\n" + "=" * 80)
        print("📊 TODOS LOS CAMPOS DEL CLIENTE:")
        print("=" * 80)

        campos_relevantes = []

        for key, value in sorted(cliente.items()):
            # Filtrar campos que podrían tener descuento
            if any(
                x in key.lower()
                for x in [
                    "discount",
                    "descuento",
                    "group",
                    "price",
                    "tax",
                    "porcentaje",
                    "percent",
                ]
            ):
                campos_relevantes.append((key, value))
                print(f"🎯 [{key}] = {value}")
            else:
                print(f"   [{key}] = {value}")

        # Resumen de campos relevantes
        print("\n" + "=" * 80)
        print("🎯 CAMPOS POTENCIALMENTE RELACIONADOS CON DESCUENTOS:")
        print("=" * 80)

        if campos_relevantes:
            for key, value in campos_relevantes:
                print(f"✓ {key} = {value}")
        else:
            print(
                "⚠️ No se encontraron campos con palabras clave (discount, descuento, group, etc.)"
            )

        # Obtener más clientes para comparar
        print("\n" + "=" * 80)
        print("📊 COMPARACIÓN CON 5 CLIENTES MÁS:")
        print("=" * 80)

        resultado = conn.get(
            "BusinessPartners",
            {"$filter": "CardType eq 'cCustomer' and Valid eq 'tYES'", "$top": 5},
        )

        if resultado and "value" in resultado:
            for idx, cli in enumerate(resultado["value"], 1):
                print(f"\n{idx}. {cli.get('CardCode')} - {cli.get('CardName')}")
                for key in [k for k, v in campos_relevantes]:
                    valor = cli.get(key, "N/A")
                    print(f"   {key}: {valor}")

        # Investigar tablas relacionadas
        print("\n" + "=" * 80)
        print("🔎 INVESTIGANDO TABLAS RELACIONADAS:")
        print("=" * 80)

        # Intentar obtener datos de precio/descuento
        print("\n1️⃣ Intentando acceder a PriceList...")
        try:
            precio_lista = conn.get("PriceLists", {"$top": 1})
            if precio_lista and "value" in precio_lista:
                print("   ✓ PriceLists disponible")
                if precio_lista["value"]:
                    print(f"   Ejemplo: {precio_lista['value'][0]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print("\n2️⃣ Intentando acceder a CreditCardPaymentMethods...")
        try:
            credito = conn.get("SpecialPrices", {"$top": 1})
            if credito:
                print("   ✓ SpecialPrices disponible")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print("\n3️⃣ Campos de cálculo automático en BusinessPartners:")
        print(
            "   - Busca campos como: DiscountPercent, DiscountGroup, PriceListNum, TaxGroup, etc."
        )

        print("\n" + "=" * 80)
        print("✅ INVESTIGACIÓN COMPLETADA")
        print("=" * 80)
        print("\n📝 INSTRUCCIONES SIGUIENTES:")
        print("1. Revisa los campos marcados con 🎯 arriba")
        print("2. Identifica cuál es el descuento (puede ser porcentaje o grupo)")
        print("3. Comenta en el código de agente.py:")
        print("   - Campo de descuento: _____")
        print("   - Campo de grupo descuento: _____")
        print("4. Se agregará a agentepdf.py en la tabla de reportes")

    finally:
        conn.logout()


if __name__ == "__main__":
    investigar_campos_cliente()
