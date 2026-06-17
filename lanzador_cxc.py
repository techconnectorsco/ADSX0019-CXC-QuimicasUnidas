#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
lanzador_cxc.py — Decide si HOY corresponde ejecutar el RPA de CxC (main.py)
y, de ser asi, lo lanza.

Reglas:
  - Corre los dias 15 y 30 de cada mes.
  - Si el dia objetivo cae SABADO  -> se adelanta al VIERNES (dia -1).
  - Si el dia objetivo cae DOMINGO -> se aplaza al LUNES    (dia +1).
  - Febrero no tiene 30: el objetivo "30" usa el ultimo dia del mes (28/29).

Pensado para correr TODOS los dias a las 8:00 a.m. desde el Task Scheduler de Windows.
Si hoy no es dia de corrida, no hace nada (sale con codigo 0).

Uso:
  python lanzador_cxc.py                  # decide con la fecha de hoy y lanza si corresponde
  python lanzador_cxc.py --dry-run        # solo informa la decision, NO lanza main.py
  python lanzador_cxc.py --fecha 2026-11-30   # simula esa fecha (para validar la logica)
  python lanzador_cxc.py --listar 12      # imprime las proximas corridas de N meses y sale
"""

import os
import sys
import calendar
import argparse
import subprocess
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(BASE_DIR, "main.py")

# Dias del mes en que toca correr el proceso
DIAS_OBJETIVO = [15, 30]

DIAS_ES = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _dia_real(anio: int, mes: int, objetivo: int) -> int:
    """Si el mes no llega al dia objetivo (ej. 30 en febrero), usa el ultimo dia."""
    ultimo = calendar.monthrange(anio, mes)[1]
    return min(objetivo, ultimo)


def fecha_efectiva(anio: int, mes: int, objetivo: int) -> date:
    """Fecha real de ejecucion para un objetivo, ajustando fines de semana."""
    f = date(anio, mes, _dia_real(anio, mes, objetivo))
    wd = f.weekday()  # 0=lun ... 5=sab, 6=dom
    if wd == 5:  # sabado  -> viernes
        f -= timedelta(days=1)
    elif wd == 6:  # domingo -> lunes
        f += timedelta(days=1)
    return f


def corridas_del_mes(anio: int, mes: int):
    """Lista de (objetivo, fecha_efectiva) del mes dado."""
    return [(o, fecha_efectiva(anio, mes, o)) for o in DIAS_OBJETIVO]


def decidir(hoy: date):
    """Devuelve (debe_ejecutar: bool, motivo: str)."""
    # Candidatas: las corridas de este mes + el "30" del mes anterior, por si un
    # domingo 30 se aplazo al lunes y ese lunes ya cae en el mes siguiente.
    primer_dia = hoy.replace(day=1)
    mes_ant = primer_dia - timedelta(days=1)

    candidatas = corridas_del_mes(hoy.year, hoy.month)
    candidatas.append((30, fecha_efectiva(mes_ant.year, mes_ant.month, 30)))

    for objetivo, f in candidatas:
        if f == hoy:
            return True, (
                f"Hoy {hoy.isoformat()} ({DIAS_ES[hoy.weekday()]}) corresponde a la "
                f"corrida del dia {objetivo} (fecha efectiva ya ajustada)."
            )
    return (
        False,
        f"Hoy {hoy.isoformat()} ({DIAS_ES[hoy.weekday()]}) no es dia de corrida.",
    )


def lanzar_main() -> int:
    if not os.path.exists(MAIN_PY):
        print(f"[ERROR] No se encontro main.py en: {MAIN_PY}")
        return 1
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # evita crashes por acentos/enies al redirigir
    print(f"[INFO] Lanzando: {sys.executable} {MAIN_PY}")
    proc = subprocess.run([sys.executable, MAIN_PY], cwd=BASE_DIR, env=env)
    print(f"[INFO] main.py finalizo con codigo {proc.returncode}")
    return proc.returncode


def imprimir_proximas(n_meses: int):
    hoy = date.today()
    anio, mes = hoy.year, hoy.month
    print(f"Proximas corridas ({n_meses} meses) - objetivos {DIAS_OBJETIVO}:")
    for _ in range(n_meses):
        for objetivo, f in corridas_del_mes(anio, mes):
            real = _dia_real(anio, mes, objetivo)
            natural = date(anio, mes, real)
            nota = ""
            if f != natural:
                nota = " (ajustado por fin de semana)"
            if real != objetivo:
                nota += " (mes corto: usa ultimo dia)"
            print(
                f"  {anio}-{mes:02d} dia {objetivo:>2}: corre el "
                f"{f.isoformat()} ({DIAS_ES[f.weekday()]}){nota}"
            )
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1


def main():
    ap = argparse.ArgumentParser(
        description="Lanzador del RPA CxC (dias 15 y 30, con ajuste de fin de semana)."
    )
    ap.add_argument("--fecha", help="Simular una fecha YYYY-MM-DD (para validar).")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo informa la decision, no lanza main.py.",
    )
    ap.add_argument(
        "--listar",
        type=int,
        metavar="N",
        help="Imprime las proximas corridas de N meses y sale.",
    )
    args = ap.parse_args()

    if args.listar:
        imprimir_proximas(args.listar)
        return

    if args.fecha:
        try:
            hoy = date.fromisoformat(args.fecha)
        except ValueError:
            print("[ERROR] Formato de fecha invalido. Usa YYYY-MM-DD.")
            sys.exit(2)
    else:
        hoy = date.today()

    debe, motivo = decidir(hoy)
    print(f"[{hoy.isoformat()}] {motivo}")

    if not debe:
        return
    if args.dry_run:
        print("[DRY-RUN] Correspondia ejecutar, pero no se lanza por --dry-run.")
        return

    sys.exit(lanzar_main())


if __name__ == "__main__":
    main()
