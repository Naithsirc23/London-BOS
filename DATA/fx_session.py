"""
Análisis de la sesión asiática del par EUR/USD para la estrategia London-BOS.

La sesión asiática es el rango de consolidación ANTES de la apertura de Londres:
  - Inicio: 19:00 (Lima) del día anterior  = apertura de Tokio (09:00 JST)
  - Fin   : apertura de Londres (08:00 local) convertida a Lima
            = 02:00 Lima en verano (BST) / 03:00 Lima en invierno (GMT)
            Lima no tiene DST; solo cambia el horario de Londres.

FUENTE DE DATOS (2026-07-17): IB Gateway vía ib_insync (reqHistoricalData).
  Reemplaza a yfinance, que solo daba 1m para ~7 días. IB da histórico largo.
  El gateway debe estar abierto en localhost (puerto 4001 paper / 4002 live).
  yfinance queda como fallback si no hay gateway.

Uso:
    .venv/bin/python fx_session.py [--date YYYY-MM-DD] [--port 4001] [--client 1]
    (sin args: usa "ayer" en Lima, puerto 4001, client 1)
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta

import pytz

lima_tz = pytz.timezone("America/Lima")
ldn_tz = pytz.timezone("Europe/London")


def ventana_asiatica(fecha_lima: datetime) -> tuple[datetime, datetime]:
    """Devuelve (inicio, fin) de la sesión asiática en hora Lima.

    inicio = 19:00 Lima del día anterior a `fecha_lima`
    fin    = 08:00 local de Londres del mismo día, convertido a Lima
    """
    inicio = lima_tz.localize(
        datetime(fecha_lima.year, fecha_lima.month, fecha_lima.day, 19, 0, 0)
    ) - timedelta(days=1)
    fin_ldn_local = ldn_tz.localize(
        datetime(fecha_lima.year, fecha_lima.month, fecha_lima.day, 8, 0)
    )
    fin = fin_ldn_local.astimezone(lima_tz)
    return inicio, fin


def cargar_ib(inicio: datetime, fin: datetime, port: int, client: int):
    """Descarga EURUSD 1m desde IB Gateway. Devuelve DataFrame tz-aware en Lima."""
    from ib_insync import IB, Forex
    import pandas as pd

    ib = IB()
    try:
        ib.connect("127.0.0.1", port, clientId=client, timeout=15)
    except Exception as e:
        print(f"[IB] No se pudo conectar al gateway en puerto {port}: {e}")
        return None

    contrato = ib.qualifyContracts(Forex("EURUSD"))
    if not contrato:
        print("[IB] No se pudo calificar el contrato EURUSD.")
        ib.disconnect()
        return None

    # pedir 2 días para cubrir la ventana (Tokio ayer 19:00 -> Londres hoy 08:00)
    end = fin.astimezone(pytz.UTC)
    bars = ib.reqHistoricalData(
        contrato[0],
        endDateTime=end.strftime("%Y%m%d %H:%M:%S"),
        durationStr="2 D",
        barSizeSetting="1 min",
        whatToShow="MIDPOINT",
        useRTH=False,
        formatDate=1,
    )
    ib.disconnect()
    if not bars:
        print("[IB] Sin barras históricas.")
        return None

    df = pd.DataFrame(
        [(b.date, b.open, b.high, b.low, b.close) for b in bars],
        columns=["date", "Open", "High", "Low", "Close"],
    )
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    df.index = df.index.tz_convert(lima_tz)
    print("[IB] Datos descargados desde IB Gateway.")
    return df


def cargar_yfinance(inicio: datetime, fin: datetime):
    """Fallback: yfinance 1m (~7 días máximo)."""
    import yfinance as yf
    import pandas as pd

    ticker = "EURUSD=X"
    data = yf.download(
        ticker,
        start=(inicio - timedelta(days=1)).strftime("%Y-%m-%d"),
        end=(fin + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1m",
        auto_adjust=False,
        progress=False,
    )
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    data.index = data.index.tz_convert(lima_tz)
    print("[yfinance] Datos descargados (fallback).")
    return data


def calcular_box(port=4001, client=1, fecha_ref=None, no_ib=False):
    """Calcula el box asiático de una fecha. Devuelve dict con los valores.

    fecha_ref: datetime en zona Lima (si None -> hoy Lima, última sesión completa).
    """
    ahora_lima = datetime.now(lima_tz)
    if fecha_ref is None:
        ref = ahora_lima
    elif isinstance(fecha_ref, str):
        y, m, d = (int(x) for x in fecha_ref.split("-"))
        ref = lima_tz.localize(datetime(y, m, d, 0, 0, 0))
    else:
        ref = fecha_ref

    inicio, fin = ventana_asiatica(ref)
    data = None
    if not no_ib:
        data = cargar_ib(inicio, fin, port, client)
    if data is None:
        data = cargar_yfinance(inicio, fin)
    if data is None or data.empty:
        return None

    sesion = data.loc[inicio:fin]
    if sesion.empty:
        return None

    maximo = float(sesion["High"].max())
    minimo = float(sesion["Low"].min())
    rango_pips = (maximo - minimo) * 10000
    en_zona = 15 <= rango_pips <= 40
    return dict(inicio=inicio, fin=fin, maximo=maximo, minimo=minimo,
                rango=rango_pips, en_zona=en_zona, nbarras=len(sesion))


def main() -> int:
    ap = argparse.ArgumentParser(description="Sesión asiática EUR/USD (London-BOS)")
    ap.add_argument("--date", help="Fecha de referencia YYYY-MM-DD (default: ayer Lima)")
    ap.add_argument("--port", type=int, default=4001, help="Puerto IB Gateway")
    ap.add_argument("--client", type=int, default=1, help="ClientID IB")
    ap.add_argument("--no-ib", action="store_true", help="Forzar yfinance")
    ap.add_argument("--html", help="Ruta de salida HTML del dashboard (ej: modulo-5-dashboard/london-bos-ahora.html)")
    args = ap.parse_args()

    box = calcular_box(port=args.port, client=args.client,
                       fecha_ref=args.date, no_ib=args.no_ib)
    if box is None:
        print("No se obtuvieron datos.")
        return 1

    inicio, fin = box["inicio"], box["fin"]
    maximo, minimo, rango_pips, en_zona = box["maximo"], box["minimo"], box["rango"], box["en_zona"]

    print("=" * 56)
    print("  SESIÓN ASIÁTICA EUR/USD  (pre-apertura de Londres)")
    print("=" * 56)
    print(f"  Inicio : {inicio.strftime('%Y-%m-%d %H:%M')} (Lima)  [Tokio]")
    print(f"  Fin    : {fin.strftime('%Y-%m-%d %H:%M')} (Lima)  [Londres]")
    print(f"  Barras : {box['nbarras']} (1m)")
    print("-" * 56)
    print(f"  MÁXIMO : {maximo:.5f}")
    print(f"  MÍNIMO : {minimo:.5f}")
    print(f"  RANGO  : {rango_pips:.1f} pips  "
          f"{'✅ operable' if en_zona else '⚠️ fuera de 15–40'}")
    print("=" * 56)

    if args.html:
        es_central = args.html.endswith("index.html")
        _volcar_html(inicio, fin, maximo, minimo, rango_pips, en_zona,
                     box["nbarras"], args.html, central=es_central)
    return 0


def _volcar_html(inicio, fin, maximo, minimo, rango_pips, en_zona, nbarras, path, central=True):
    """Genera el dashboard HTML.

    central=True  -> SPA completo (dashboard + módulos 1-4 embebidos, navegación
                     por botones sin saltar a otros archivos). Lee el template
                     DATA/dashboard_spa.html y reemplaza placeholders con datos reales.
    central=False -> widget de solo-box (london-bos-ahora.html).
    Todos los valores vienen de los datos reales de IB; nada hardcodeado.
    """
    import os
    estado = "OPERABLE" if en_zona else "NO OPERABLE"
    color = "#388E3C" if en_zona else "#D32F2F"
    icono = "✓" if en_zona else "✕"
    pos = max(0, min(100, rango_pips / 50 * 100))
    gen = datetime.now(lima_tz).strftime("%Y-%m-%d %H:%M:%S")
    fecha_ref = inicio.strftime("%Y-%m-%d")
    ini = inicio.strftime("%Y-%m-%d %H:%M")
    fin_ = fin.strftime("%Y-%m-%d %H:%M")
    dentr = "✓ DENTRO DE RANGO" if en_zona else "✕ FUERA DE RANGO"
    pillcls = "" if en_zona else "red"
    vred = "" if en_zona else "red"
    MARGIN = 0.00002
    tp_fijo = maximo + MARGIN + (maximo - minimo)  # entry + rango (modo fijo M4)

    if not central:
        # widget de solo-box (compacto, dinámico)
        html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>London BOS · Box asiático</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:#F5F5F5;color:#212121;font-family:'Roboto',sans-serif;min-height:100vh;padding:24px;display:flex;flex-direction:column;gap:20px;align-items:center;max-width:560px;margin:0 auto;}}
  .wrap{{width:100%;}}
  .topbar{{display:flex;align-items:center;justify-content:space-between;background:#FFFFFF;border-radius:14px;padding:18px 24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);}}
  .topbar .t{{font-size:18px;font-weight:900;color:#1B5E20;}}
  .topbar .t small{{display:block;font-size:11px;font-weight:500;color:#757575;letter-spacing:1px;}}
  .pill{{display:inline-flex;align-items:center;gap:8px;background:{('#E8F5E9' if en_zona else '#FFEBEE')};color:{color};font-size:14px;font-weight:700;padding:8px 14px;border-radius:30px;}}
  .pill .dot{{width:10px;height:10px;border-radius:50%;background:{color};}}
  .verdict{{background:{color};color:#FFFFFF;border-radius:16px;padding:28px 24px;display:flex;flex-direction:column;align-items:center;gap:8px;box-shadow:0 4px 14px rgba(0,0,0,0.18);}}
  .verdict .icon{{font-size:46px;font-weight:900;line-height:1;}}
  .verdict .est{{font-size:30px;font-weight:900;letter-spacing:1px;}}
  .verdict .sub{{font-size:16px;font-weight:500;opacity:0.95;}}
  .card{{background:#FFFFFF;border-radius:16px;padding:22px;box-shadow:0 2px 8px rgba(0,0,0,0.08);}}
  .card h2{{font-size:13px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#9E9E9E;margin-bottom:16px;}}
  .grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;}}
  .box{{border-radius:14px;padding:18px;text-align:center;background:#F5F5F5;}}
  .box .lab{{font-size:12px;font-weight:500;letter-spacing:1px;text-transform:uppercase;color:#757575;}}
  .box .val{{font-size:26px;font-weight:900;margin-top:6px;color:#212121;}}
  .box.rango{{background:#E8F5E9;}}
  .box.rango .val{{color:{color};font-size:34px;}}
  .bar{{position:relative;height:18px;background:#EEEEEE;border-radius:9px;margin-top:16px;}}
  .bar .zona{{position:absolute;top:0;height:100%;left:30%;width:50%;background:#C8E6C9;border-radius:9px;}}
  .bar .mark{{position:absolute;top:-5px;width:6px;height:28px;background:{color};border-radius:3px;left:{pos:.1f}%;transform:translateX(-50%);}}
  .scale{{display:flex;justify-content:space-between;font-size:12px;font-weight:500;color:#757575;margin-top:8px;}}
  .scale .ok{{color:#388E3C;font-weight:700;}}
  .meta{{display:flex;flex-direction:column;gap:10px;}}
  .meta .row{{display:flex;justify-content:space-between;font-size:15px;padding:8px 0;border-bottom:1px solid #EEEEEE;}}
  .meta .row:last-child{{border-bottom:none;}}
  .meta .k{{color:#757575;font-weight:500;}}
  .meta .v{{color:#212121;font-weight:700;}}
</style></head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="t">Box asiático en vivo<small>{fecha_ref} · SESIÓN ASIÁTICA</small></div>
      <span class="pill"><span class="dot"></span>IB {estado}</span>
    </div>
    <div class="verdict">
      <div class="icon">{icono}</div>
      <div class="est">{estado}</div>
      <div class="sub">RANGO ASIÁTICO EUR/USD · {rango_pips:.1f} pips</div>
    </div>
    <div class="card">
      <h2>Box asiático</h2>
      <div class="grid">
        <div class="box"><div class="lab">Techo</div><div class="val">{maximo:.5f}</div></div>
        <div class="box rango"><div class="lab">Rango</div><div class="val">{rango_pips:.1f}</div></div>
        <div class="box"><div class="lab">Piso</div><div class="val">{minimo:.5f}</div></div>
      </div>
      <div class="bar"><div class="zona"></div><div class="mark"></div></div>
      <div class="scale"><span>0</span><span class="ok">zona 15–40 pips</span><span>50</span></div>
    </div>
    <div class="card">
      <h2>Ventana</h2>
      <div class="meta">
        <div class="row"><span class="k">Inicio (Tokio)</span><span class="v">{ini} Lima</span></div>
        <div class="row"><span class="k">Fin (Londres)</span><span class="v">{fin_} Lima</span></div>
        <div class="row"><span class="k">Barras 1m</span><span class="v">{nbarras}</span></div>
        <div class="row"><span class="k">Generado</span><span class="v">{gen}</span></div>
      </div>
    </div>
  </div>
</body></html>"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[HTML] Dashboard generado: {path}")
        return

    # ---- central: SPA desde template ----
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_spa.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    repl = {
        "__FECHA__": fecha_ref, "__ESTADO__": estado, "__ICONO__": icono,
        "__RANGO__": f"{rango_pips:.1f}", "__MAX__": f"{maximo:.5f}",
        "__MIN__": f"{minimo:.5f}", "__POS__": f"{pos:.1f}",
        "__INI__": ini, "__FIN__": fin_, "__NBAR__": str(nbarras),
        "__COLOR__": color, "__DENTRO__": dentr, "__GEN__": gen,
        "__PILLCLS__": pillcls, "__VRED__": vred, "__TP__": f"{tp_fijo:.5f}",
        "__PAPER_ROWS__": _leer_paper_rows(),
        "__LOG_ROWS__": _leer_log_rows(),
        "__HOY__": datetime.now(lima_tz).strftime("%d/%m/%Y"),
        "__LOG_FECHA__": _leer_log_fecha_reciente() or fecha_ref,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(tpl)
    print(f"[HTML] Dashboard generado: {path}")
    # registrar en el logger (M7)
    _log_sesion(inicio, maximo, minimo, rango_pips, en_zona, nbarras)
    # inyectar fecha real en módulos sueltos M2/M4
    _actualizar_modulos_sueltos(fecha_ref)


def _leer_log_fecha_reciente():
    """Devuelve la fecha (YYYY-MM-DD) de la sesión más reciente en el logger (M7).
    Si no hay registros, devuelve None."""
    import sqlite3, os
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    try:
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT fecha FROM sesiones ORDER BY fecha DESC LIMIT 1").fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def _leer_log_rows():
    """Lee las sesiones de SQLite y devuelve filas HTML para el Módulo 7."""
    import sqlite3, os
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT fecha, maximo, minimo, rango_pips, operable, barras, "
            "ruptura_20, ruptura_60 "
            "FROM sesiones ORDER BY fecha DESC LIMIT 30").fetchall()
        con.close()
    except Exception:
        return '<div class="note">Sin registros aún. Genera el dashboard para guardar la sesión de hoy.</div>'
    if not rows:
        return '<div class="note">Sin registros aún. Genera el dashboard para guardar la sesión de hoy.</div>'
    head = ('<div class="tbl-row head"><div>Fecha</div><div>Techo</div><div>Piso</div>'
            '<div>Rango</div><div>Op.</div><div>20m</div><div>60m</div></div>')
    body = ""
    for f, mx, mn, rp, op, br, r20, r60 in rows:
        opc = "✅" if op else "❌"
        opcls = "y" if op else "n"
        a = lambda x: x if x else "—"
        body += (f'<div class="tbl-row"><div>{f}</div><div>{mx:.5f}</div>'
                  f'<div>{mn:.5f}</div><div>{rp:.1f}</div>'
                  f'<div class="op {opcls}">{opc}</div>'
                  f'<div class="rpt">{a(r20)}</div>'
                  f'<div class="rpt">{a(r60)}</div></div>')
    return head + body


def _leer_paper_rows():
    """Lee los paper trades de SQLite y devuelve filas HTML para el Módulo 7."""
    import sqlite3, os
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT fecha, direccion, entry, salida, r FROM paper "
            "ORDER BY fecha DESC LIMIT 30").fetchall()
        con.close()
    except Exception:
        return '<div class="note">Sin paper trades aún. Corre DATA/paper_trade.py para simular.</div>'
    if not rows:
        return '<div class="note">Sin paper trades aún. Corre DATA/paper_trade.py para simular.</div>'
    head = ('<div class="tbl-row head"><div>Fecha</div><div>Dir</div><div>Entry</div>'
            '<div>Salida</div><div>R</div></div>')
    body = ""
    for f, d, e, s, r in rows:
        if e is None:
            body += (f'<div class="tbl-row"><div>{f}</div><div>—</div>'
                      f'<div>—</div><div>{s}</div><div>—</div></div>')
            continue
        rcls = "y" if (r is not None and r >= 0) else "n"
        rtxt = f"{r:+.2f}" if r is not None else "—"
        body += (f'<div class="tbl-row"><div>{f}</div><div>{d}</div>'
                  f'<div>{e:.5f}</div><div>{s}</div>'
                  f'<div class="op {rcls}">{rtxt}</div></div>')
    return head + body


def _log_sesion(inicio, maximo, minimo, rango_pips, en_zona, nbarras):
    """Registra la sesión y emite un evento estructurado para el dashboard."""
    import os
    from londonbos_core.storage import record_event

    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    fecha = inicio.strftime("%Y-%m-%d")
    generado = datetime.now(lima_tz)
    try:
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("""CREATE TABLE IF NOT EXISTS sesiones (
            fecha TEXT PRIMARY KEY, maximo REAL, minimo REAL,
            rango_pips REAL, operable INTEGER, barras INTEGER,
            generado TEXT, ruptura_20 TEXT, ruptura_60 TEXT)""")
        con.execute("""INSERT INTO sesiones (fecha, maximo, minimo, rango_pips,
            operable, barras, generado, ruptura_20, ruptura_60)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(fecha) DO UPDATE SET maximo=excluded.maximo,
            minimo=excluded.minimo, rango_pips=excluded.rango_pips,
            operable=excluded.operable, barras=excluded.barras,
            generado=excluded.generado""",
            (fecha, maximo, minimo, rango_pips, 1 if en_zona else 0,
             nbarras, generado.strftime("%Y-%m-%d %H:%M:%S"), None, None))
        con.commit()
        con.close()
        record_event(
            db,
            "SESSION_RECORDED",
            timestamp=generado,
            session_date=fecha,
            source="fx_session",
            metadata={
                "high": maximo,
                "low": minimo,
                "range_pips": rango_pips,
                "operable": bool(en_zona),
                "bars": nbarras,
            },
        )
        print(f"[LOG] Sesión {fecha} registrada en logger y eventos.")
    except Exception as e:
        print(f"[LOG] No se pudo registrar (no bloquea): {e}")


def _actualizar_modulos_sueltos(fecha_ref):
    """Inyecta la fecha real del box asiático (__FECHA__) en los módulos sueltos
    M2 (escáner) y M4 (órdenes), para que muestren la fecha real en su badge
    'Información de fecha' en lugar de 'hoy' o un placeholder vacío.
    No toca M1/M3 (en vivo / interactivos)."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz London-BOS
    objetivos = [
        os.path.join(base, "modulo-2-escaner", "index.html"),
        os.path.join(base, "modulo-4-ordenes", "london-bos-modulo4.html"),
    ]
    for path in objetivos:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            # solo reemplaza el data-date del placeholder (no otros usos de __FECHA__)
            nuevo = html.replace('data-date="__FECHA__"', f'data-date="{fecha_ref}"')
            if nuevo != html:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(nuevo)
                print(f"[HTML] Módulo suelto actualizado: {os.path.basename(os.path.dirname(path))}")
        except Exception as e:
            print(f"[HTML] No se pudo actualizar {path}: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
