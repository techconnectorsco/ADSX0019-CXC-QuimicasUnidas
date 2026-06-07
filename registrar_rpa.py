"""
Script de UN SOLO USO.
Registra el RPA de Químicas Unidas en Supabase y te devuelve su UUID
para que lo pegues en supabase_manager.py -> ID_RPA_QU.

IMPORTANTE: ajusta las columnas de 'nuevo_rpa' a las que realmente tenga
tu tabla 'automatizaciones'. Para verlas, mira una fila existente
(la de Vedoba o Magaya) en el dashboard de Supabase.
"""

from conexion_supabase import supabase_db

nuevo_rpa = {
    "cliente_id": "ac25d613-7d58-4a4f-b909-0342050376c8",
    "nombre": "Químicas Unidas ADSX0019 - CxC",
    "descripcion": "Automatización RPA para gestión de Cuentas por Cobrar en Químicas Unidas, ejecutada el 15 y 30 de cada mes.",
    "tipo": "RPA",
    "repo_url": "https://github.com/techconnectorsco/ADSX0019-CXC-QuimicasUnidas.git",
    "frecuencia": "Quincenal (15 y 30 de cada mes)",
}

res = supabase_db.table("automatizaciones").insert(nuevo_rpa).execute()

print("✅ RPA registrado. Copia este id en supabase_manager.py -> ID_RPA_QU:")
print(res.data)
