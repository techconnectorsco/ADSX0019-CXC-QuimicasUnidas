"""
Niveles 2 y 3 del plan de pruebas de "Giras por Zona" (PLAN_GIRAS_POR_ZONA.md, sección 9).

Reemplaza los curl del plan, que en PowerShell son incómodos de escribir por las
comillas. Habla con la API por HTTP; no importa agentes.py ni api.py.

    # El arbol de un agente, con la elegibilidad resuelta. Solo lectura.
    python tests/prueba_gira_zona_endpoint.py arbol --agente 7
    python tests/prueba_gira_zona_endpoint.py arbol --agente 7 --refrescar

    # Nivel 2 — validación de parámetros. No encola nada, no toca SAP.
    python tests/prueba_gira_zona_endpoint.py validacion

    # Comprobar en qué modo está el módulo antes de disparar nada
    python tests/prueba_gira_zona_endpoint.py config

    # Nivel 3 — SAP sí, correo no. Genera el PDF y espera el resultado.
    python tests/prueba_gira_zona_endpoint.py dry-run --agente 9 --clientes C0476
    python tests/prueba_gira_zona_endpoint.py dry-run --agente 7 --clientes C0163 \
        --zona "COLONO AGROP-ALM COLONO BM"

⚠️  ADVERTENCIA: la API apunta a SAP PRODUCCIÓN y a Microsoft Graph real.
    Este script NUNCA manda solo_prueba=False sin dry_run. El envío real se
    hace a mano, después de bajar GIRA_ZONA_FORZAR_DRY_RUN en agentes.py.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# La consola de Windows viene en cp1252 y revienta con los emoji de los mensajes.
# Mismo parche que usa api.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_POR_DEFECTO = "http://127.0.0.1:8050"


def _pedir(base, ruta, cuerpo=None, timeout=30):
    url = f"{base}{ruta}"
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(
        url,
        data=datos,
        headers={"Content-Type": "application/json"} if datos else {},
        method="POST" if datos else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")
    except urllib.error.URLError as e:
        print(f"❌ No se pudo contactar {url}: {e.reason}")
        print("   ¿Está corriendo la API?  python api.py")
        sys.exit(1)


def cmd_arbol(args):
    """
    GET /api/arbol-gira-zona — el arbol con la elegibilidad resuelta.

    Solo lectura: no encola nada. Es el endpoint que reemplaza a
    obtenerArbolAgente() de sap.ts, que armaba el arbol por SalesPersonCode de
    la ficha en vez de por el ruteo real del documento.

    El timeout es alto a proposito: con el cache frio hay que esperar el
    barrido del mapa, que en horario de oficina son ~100s.
    """
    ruta = f"/api/arbol-gira-zona?agente={args.agente}"
    if args.refrescar:
        ruta += "&refrescar=1"

    inicio = time.time()
    estado, datos = _pedir(args.base, ruta, timeout=args.timeout)
    segs = time.time() - inicio

    if datos.get("error"):
        print(f"❌ {datos['error']}")
        return 1

    agente = datos.get("agente") or {}
    print(f"Agente {agente.get('codigo')} — {agente.get('nombre')}")
    print(f"HTTP {estado} en {segs:.1f}s")
    print("")
    print(f"   Elegibles    : {datos.get('totalElegibles')}")
    print(f"   En gris      : {datos.get('totalNoElegibles')}")
    print(f"   Zonas        : {len(datos.get('zonas') or [])}")
    print(f"   Sin zona     : {len(datos.get('sinZona') or [])}")
    if datos.get("montosAproximados"):
        print("   Los montos son APROXIMADOS (redondeo de /SQLQueries).")

    for z in datos.get("zonas") or []:
        zona = z["zona"]
        print("")
        print(f"   --- {zona['codigo']}  {zona['nombre']}"
              f"   ({z['totalElegibles']} elegibles,"
              f" {z['totalNoElegibles']} en gris)")
        for c in z["clientes"]:
            if c["elegible"]:
                marca = f"{c['docs']:>3} docs  CRC {c['crc']:>14,.2f}"
                if c["usd"]:
                    marca += f"  USD {c['usd']:>10,.2f}"
            else:
                motivo = c.get("motivo") or "?"
                if c.get("vendedorNombre"):
                    motivo += f" ({c['vendedorNombre']})"
                marca = f"  --   en gris: {motivo}"
            print(f"      {c['cardCode']:<8} {c['cardName'][:38]:<38} {marca}")

    if datos.get("sinZona"):
        print("")
        print("   --- Sin zona asignada")
        for c in datos["sinZona"]:
            print(f"      {c['cardCode']:<8} {c['cardName'][:38]}")

    return 0


def cmd_config(args):
    estado, datos = _pedir(args.base, "/api/config-gira-zona")
    print(json.dumps(datos, indent=2, ensure_ascii=False))
    if datos.get("forzar_dry_run"):
        print("\n🧪 El módulo está en MODO ENSAYO: no envía correo ni sube a SharePoint.")
    else:
        print("\n🔴 ATENCIÓN: el modo ensayo está APAGADO. Un envío sería real.")


def cmd_validacion(args):
    """Nivel 2: todo esto debe rechazarse ANTES de encolar."""
    casos = [
        ("agente vacío", {"agente_codigo": "", "card_codes": ["C0001"]}),
        ("agente no numérico", {"agente_codigo": "abc", "card_codes": ["C0001"]}),
        ("lista de clientes vacía", {"agente_codigo": "9", "card_codes": []}),
        (
            "revisión sin correo_destino",
            {"agente_codigo": "9", "card_codes": ["C0001"], "solo_prueba": True},
        ),
    ]

    print("=" * 72)
    print("NIVEL 2 — validación de parámetros (no encola, no toca SAP)")
    print("=" * 72)

    fallos = 0
    for nombre, cuerpo in casos:
        _, datos = _pedir(args.base, "/api/ejecutar-gira-zona", cuerpo)
        ok = datos.get("estado") == "error"
        print(f"{'✅' if ok else '❌'} {nombre:<28} → {datos.get('mensaje')}")
        if not ok:
            fallos += 1
            print(f"   ⚠️ SE ENCOLÓ UNA TAREA. job_id={datos.get('job_id')}")

    print()
    print("✅ Nivel 2 completo." if not fallos else f"❌ {fallos} caso(s) no rechazados.")
    return 1 if fallos else 0


def cmd_dry_run(args):
    print("=" * 72)
    print("NIVEL 3 — SAP sí, correo no")
    print("=" * 72)

    _, cfg = _pedir(args.base, "/api/config-gira-zona")
    print(f"   forzar_dry_run del módulo: {cfg.get('forzar_dry_run')}")

    cuerpo = {
        "agente_codigo": str(args.agente),
        "card_codes": args.clientes,
        "solo_prueba": False,
        "correo_destino": None,
        "zona_nombre": args.zona,
        "dry_run": True,  # explícito además del interruptor del módulo
    }
    print(f"   Agente {args.agente} · {len(args.clientes)} cliente(s): {', '.join(args.clientes)}")
    print()

    _, datos = _pedir(args.base, "/api/ejecutar-gira-zona", cuerpo)
    if datos.get("estado") != "exito":
        print(f"❌ Rechazado: {datos.get('mensaje')}")
        return 1

    job_id = datos["job_id"]
    print(f"🕐 Encolado como {job_id}. Esperando...")

    inicio = time.time()
    while time.time() - inicio < args.timeout:
        time.sleep(3)
        _, estado = _pedir(args.base, f"/api/estado-gira-zona/{job_id}")
        situacion = estado.get("estado")
        print(f"   [{int(time.time() - inicio):>3}s] {situacion}", end="\r")

        if situacion in ("terminado", "con_avisos", "error"):
            print()
            print(json.dumps(estado, indent=2, ensure_ascii=False))
            r = estado.get("resultado") or {}
            print()
            print(f"   solicitados: {r.get('solicitados')}")
            print(f"   procesados:  {r.get('procesados')}")
            print(f"   omitidos:    {r.get('omitidos')}")
            print(f"   pdf:         {r.get('pdf')}")
            print(f"   enviado_a:   {r.get('enviado_a')}  (debe ser None en dry run)")
            if r.get("enviado_a"):
                print("   🔴 SE ENVIÓ UN CORREO. Revisar GIRA_ZONA_FORZAR_DRY_RUN.")
                return 1
            return 0

    print(f"\n⚠️ Sin respuesta tras {args.timeout}s. Mirá los logs de la API.")
    return 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=BASE_POR_DEFECTO, help=f"URL de la API (def. {BASE_POR_DEFECTO})")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("arbol", help="El árbol de un agente (solo lectura)")
    a.add_argument("--agente", required=True, help="Código del vendedor. Ej: 7")
    a.add_argument("--refrescar", action="store_true",
                   help="Tira el caché y vuelve a barrer SAP")
    a.add_argument("--timeout", type=int, default=300,
                   help="Segundos de espera (def. 300; el caché frío tarda)")

    sub.add_parser("config", help="Ver en qué modo está el módulo")
    sub.add_parser("validacion", help="Nivel 2 — parámetros inválidos")

    d = sub.add_parser("dry-run", help="Nivel 3 — genera el PDF sin enviar")
    d.add_argument("--agente", required=True, help="Código del vendedor. Ej: 9")
    d.add_argument("--clientes", required=True, nargs="+", help="CardCodes. Ej: C0163 C0042")
    d.add_argument("--zona", default=None, help="Nombre de zona para el encabezado")
    d.add_argument("--timeout", type=int, default=300, help="Segundos de espera (def. 300)")

    args = p.parse_args()
    fn = {
        "arbol": cmd_arbol,
        "config": cmd_config,
        "validacion": cmd_validacion,
        "dry-run": cmd_dry_run,
    }[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
