"""Módulo · Paper Trade (Opción B: simulación local con datos reales).

Toma el box asiático de una fecha, calcula niveles 1.5R (Buy/Sell Stop + SL + TP),
y simula el ciclo de gestión canónico (M5: BE+1R, TP fijo +1.5R, corte 11:00) usando
las barras reales de 1m de EUR/USD desde la apertura de Londres (02:00 Lima)
hasta las 11:00 Lima. No ejecuta nada en IB; es paper 100% local.

Uso:
  DATA/.venv/bin/python DATA/paper_trade.py [--date YYYY-MM-DD] [--port 4001] [--client N]
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx_session as fx

LIMA = timezone(timedelta(hours=-5))
MARGIN = 0.00020       # 2 pips buffer para entry (0.00020 = 2.0 pips)
CIERRE = 11            # hora Lima de cierre forzoso


def barras_dia(fecha_lima, hasta_hora=11):
    """Barras 1m de EUR/USD de 02:00 a `hasta_hora` Lima de la fecha, vía yfinance."""
    try:
        import yfinance as yf
        start = fecha_lima.replace(hour=2, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        hh = int(hasta_hora)
        mm = int(round((hasta_hora - hh) * 60))
        end = fecha_lima.replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone(timezone.utc)
        df = yf.download("EURUSD=X",
                         start=start, end=end,
                         interval="1m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []
        # aplanar MultiIndex si existe
        if hasattr(df.columns, "droplevel"):
            try:
                df.columns = df.columns.droplevel(1)
            except Exception:
                pass
        out = []
        for ts, row in df.iterrows():
            t = ts
            if t.tzinfo is not None:
                t = t.astimezone(LIMA)
            out.append((t, float(row["Close"])))
        return out
    except Exception as e:
        print(f"  [barras] error: {e}")
        return []


def simular(box, barras):
    """Simula el ciclo M5 sobre las barras reales. Devuelve dict de resultado.
    Gestión canónica: BE a +1R, TP fijo +1.5R, SL opuesto del box, corte 11:00 Lima.
    Sin parcial +2R ni trailing."""
    mx, mn = box["maximo"], box["minimo"]
    buy_entry = mx + MARGIN
    sell_entry = mn - MARGIN
    risk = abs(buy_entry - mn)
    tp_buy = buy_entry + 1.5 * risk
    tp_sell = sell_entry - 1.5 * risk

    # estados
    direccion = None
    entry = sl = tp = None
    be_hecho = False
    sl_actual = None
    salida = None
    r_final = None
    hitos = []

    for t, precio in barras:
        if direccion is None:
            # detectar ruptura
            if precio >= buy_entry:
                direccion = "BUY"
                entry, sl, tp = buy_entry, mn, tp_buy
                sl_actual = sl
                hitos.append(("entry", t, precio))
            elif precio <= sell_entry:
                direccion = "SELL"
                entry, sl, tp = sell_entry, mx, tp_sell
                sl_actual = sl
                hitos.append(("entry", t, precio))
            continue

        if direccion == "BUY":
            # TP (antes que BE para priorizar salida completa)
            if precio >= tp:
                salida = "TP"; r_final = 1.5; hitos.append(("tp", t, precio)); break
            # SL (antes de BE)
            if (not be_hecho) and precio <= sl_actual:
                salida = "SL"; r_final = -1.0; hitos.append(("sl", t, precio)); break
            # BE +1R
            if (not be_hecho) and precio >= entry + risk:
                be_hecho = True
                sl_actual = entry
                hitos.append(("be", t, precio))
        else:  # SELL
            # TP (antes que BE)
            if precio <= tp:
                salida = "TP"; r_final = 1.5; hitos.append(("tp", t, precio)); break
            # SL (antes de BE)
            if (not be_hecho) and precio >= sl_actual:
                salida = "SL"; r_final = -1.0; hitos.append(("sl", t, precio)); break
            # BE +1R
            if (not be_hecho) and precio <= entry - risk:
                be_hecho = True
                sl_actual = entry
                hitos.append(("be", t, precio))

    # cierre forzoso 11:00
    if salida is None and direccion is not None:
        t_ult, p_ult = barras[-1]
        if direccion == "BUY":
            r_final = (p_ult - entry) / risk
        else:
            r_final = (entry - p_ult) / risk
        salida = "ABIERTA_11H"

    return dict(direccion=direccion or "SIN_RUPTURA", entry=entry, sl=sl, tp=tp,
                salida=salida, r=r_final, hitos=hitos)


def guardar_paper(fecha, res):
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS paper (
        fecha TEXT PRIMARY KEY, direccion TEXT, entry REAL, sl REAL, tp REAL,
        salida TEXT, r REAL)""")
    con.execute("""INSERT INTO paper (fecha, direccion, entry, sl, tp, salida, r)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(fecha) DO UPDATE SET direccion=excluded.direccion,
        entry=excluded.entry, sl=excluded.sl, tp=excluded.tp,
        salida=excluded.salida, r=excluded.r""",
        (fecha, res["direccion"], res["entry"], res["sl"], res["tp"],
         res["salida"], res["r"]))
    con.commit()
    con.close()
    # Log PAPER_TRADE_COMPLETED event with structured metadata
    try:
        import job_logger
        job_logger.log_event(
            "PAPER_TRADE_COMPLETED",
            symbol="EURUSD",
            price=res["entry"],
            metadata=f"fecha={fecha},direccion={res['direccion']},salida={res['salida']},r={res['r']}",
            metadata_json={
                "schema_version": 1,
                "fecha": fecha,
                "direccion": res["direccion"],
                "entry": res["entry"],
                "sl": res["sl"],
                "tp": res["tp"],
                "salida": res["salida"],
                "r": res["r"],
                "hitos": [{"tipo": h[0], "hora": h[1].strftime("%H:%M"), "precio": h[2]} for h in res.get("hitos", [])],
                "estrategia": "London-BOS",
                "modo": "paper"
            }
        )
    except Exception:
        pass  # no bloquear si falla el event logging


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--hasta", default=None,
                    help="Hora Lima de corte (ej. 04:30). Simula solo hasta ahí.")
    ap.add_argument("--no-notify", action="store_true",
                    help="No enviar resumen por Telegram.")
    args = ap.parse_args()

    if args.date:
        y, m, d = (int(x) for x in args.date.split("-"))
        f = datetime(y, m, d, 0, 0, 0, tzinfo=LIMA)
    else:
        f = datetime.now(LIMA)

    # hora de corte
    if args.hasta:
        hh, mm = (int(x) for x in args.hasta.split(":"))
        hasta_hora = hh + mm / 60.0
    else:
        hasta_hora = 11

    box = fx.calcular_box(fecha_ref=f.strftime("%Y-%m-%d"))
    if not box:
        print("Sin box, aborto.")
        return
    print(f"Box {f.date()}: techo {box['maximo']:.5f} piso {box['minimo']:.5f} "
          f"rango {box['rango']:.1f}p operable={box['en_zona']}")
    if not box["en_zona"]:
        print("⚠️ Fuera de rango 15-40 pips → NO OPERABLE. Paper trade omitido.")
        if not args.no_save:
            guardar_paper(f.strftime("%Y-%m-%d"), dict(
                direccion="NO_OPERABLE", entry=None, sl=None, tp=None,
                salida="SKIP", r=None))
        if not args.no_notify:
            _notificar(f, box, None, "NO_OPERABLE")
        return

    barras = barras_dia(f, hasta_hora=hasta_hora)
    if not barras:
        print("Sin barras 1m (yfinance), aborto.")
        return
    print(f"Barras cargadas: {len(barras)} (02:00–{args.hasta or '11:00'} Lima)")

    res = simular(box, barras)
    print(f"Dirección: {res['direccion']}")
    if res["entry"]:
        print(f"  Entry {res['entry']:.5f} | SL {res['sl']:.5f} | TP {res['tp']:.5f}")
    print(f"  Salida: {res['salida']} | R: {res['r']}")
    for h in res["hitos"]:
        print(f"    • {h[0].upper()} @ {h[1].strftime('%H:%M')} ({h[2]:.5f})")

    if not args.no_save:
        guardar_paper(f.strftime("%Y-%m-%d"), res)
        print("Guardado en logger (tabla paper).")

    if not args.no_notify:
        _notificar(f, box, res, None)


def _notificar(fecha, box, res, no_operable):
    """Envía el resumen del paper trade por Telegram (Módulo 6)."""
    try:
        from notifier import Notificador
    except Exception:
        return
    n = Notificador()
    if not n.ok:
        return
    if no_operable:
        msg = (f"🟢 <b>London BOS · Paper {fecha.strftime('%Y-%m-%d')}</b>\n"
               f"🔴 <b>NO OPERABLE</b> · rango {box['rango']:.1f} pips "
               f"fuera de 15-40\nPaper trade omitido.")
        n.enviar(msg)
        return
    # resumen normal
    if not res or res["direccion"] in ("SIN_RUPTURA", "NO_OPERABLE"):
        estado = "Sin ruptura en la ventana evaluada"
        r_txt = "—"
    else:
        dir_emoji = "🟢 BUY" if res["direccion"] == "BUY" else "🔴 SELL"
        salida_map = {
            "TP": "✅ TP 1.5R", "SL": "❌ SL -1.0R",
            "ABIERTA_11H": "⏳ Abierta al corte",
        }
        estado = salida_map.get(res["salida"], res["salida"])
        r_txt = f"{res['r']:+.2f}R" if res["r"] is not None else "—"
    hitos = "".join(
        f"\n    • {h[0].upper()} @ {h[1].strftime('%H:%M')}"
        for h in (res["hitos"] if res else [])
    )
    msg = (f"🟢 <b>London BOS · Paper {fecha.strftime('%Y-%m-%d')}</b>\n"
           f"Box {box['maximo']:.5f}/{box['minimo']:.5f} "
           f"rango {box['rango']:.1f}p\n"
           f"Dirección: {res['direccion'] if res else 'SIN_RUPTURA'}\n"
           f"Salida: {estado}\n"
           f"R: {r_txt}{hitos}")
    n.enviar(msg)


if __name__ == "__main__":
    main()
