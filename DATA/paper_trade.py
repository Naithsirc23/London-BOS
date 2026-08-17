"""Módulo · Paper Trade (Opción B: simulación local con datos reales).

Toma el box asiático de una fecha, calcula niveles 1.5R (Buy/Sell Stop + SL + TP),
y simula el ciclo completo de gestión (M5: BE+1R, parcial+2R, trailing) usando
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
from londonbos_core.models import Direction, SessionBox, StrategyConfig
from londonbos_core.rules import build_plan, management_thresholds

LIMA = timezone(timedelta(hours=-5))
CONFIG = StrategyConfig(target_rr=1.5, partial_rr=None)
TRAIL_STEP = CONFIG.trailing_step_pips / 10000
CIERRE = CONFIG.close_hour_lima


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
    """Simula el ciclo usando el contrato único del motor de dominio."""
    session = SessionBox(
        session_date=str(box["inicio"].date()),
        start=box["inicio"],
        end=box["fin"],
        high=box["maximo"],
        low=box["minimo"],
        bars=box.get("nbarras", 0),
        source=box.get("source", "unknown"),
    )
    buy_plan = build_plan(session, Direction.BUY, CONFIG) if box["en_zona"] else None
    sell_plan = build_plan(session, Direction.SELL, CONFIG) if box["en_zona"] else None
    buy_entry = buy_plan.entry if buy_plan else None
    sell_entry = sell_plan.entry if sell_plan else None

    # estados
    direccion = None
    entry = sl = tp = None
    risk = None
    thresholds = None
    be_hecho = parcial_hecho = False
    sl_actual = None
    salida = None
    r_final = None
    hitos = []

    for t, precio in barras:
        if direccion is None:
            # detectar ruptura
            if buy_plan and precio >= buy_plan.entry:
                direccion = "BUY"
                entry, sl, tp = buy_plan.entry, buy_plan.stop_loss, buy_plan.take_profit
                risk = buy_plan.risk_price
                thresholds = management_thresholds(buy_plan, CONFIG)
                sl_actual = sl
                hitos.append(("entry", t, precio))
            elif sell_plan and precio <= sell_plan.entry:
                direccion = "SELL"
                entry, sl, tp = sell_plan.entry, sell_plan.stop_loss, sell_plan.take_profit
                risk = sell_plan.risk_price
                thresholds = management_thresholds(sell_plan, CONFIG)
                sl_actual = sl
                hitos.append(("entry", t, precio))
            continue

        if direccion == "BUY":
            # TP
            if precio >= tp:
                salida = "TP"; r_final = CONFIG.target_rr; hitos.append(("tp", t, precio)); break
            # SL (antes de BE)
            if (not be_hecho) and precio <= sl_actual:
                salida = "SL"; r_final = -1.0; hitos.append(("sl", t, precio)); break
            # BE +1R
            if (not be_hecho) and precio >= thresholds["break_even"]:
                be_hecho = True
                sl_actual = entry
                hitos.append(("be", t, precio))
            # Parcial +2R
            if (thresholds["partial"] is not None and be_hecho and
                    (not parcial_hecho) and precio >= thresholds["partial"]):
                parcial_hecho = True
                sl_actual = entry  # duro a entry en el resto
                hitos.append(("partial", t, precio))
            # Trailing (solo si parcial hecho) cada 10 pips a favor
            if parcial_hecho:
                nuevo_sl = precio - TRAIL_STEP
                if nuevo_sl > sl_actual:
                    sl_actual = nuevo_sl
                if precio <= sl_actual:
                    salida = "TRAIL"
                    r_final = (sl_actual - entry) / risk
                    hitos.append(("trail_out", t, precio)); break
        else:  # SELL
            if precio <= tp:
                salida = "TP"; r_final = CONFIG.target_rr; hitos.append(("tp", t, precio)); break
            if (not be_hecho) and precio >= sl_actual:
                salida = "SL"; r_final = -1.0; hitos.append(("sl", t, precio)); break
            if (not be_hecho) and precio <= thresholds["break_even"]:
                be_hecho = True
                sl_actual = entry
                hitos.append(("be", t, precio))
            if (thresholds["partial"] is not None and be_hecho and
                    (not parcial_hecho) and precio <= thresholds["partial"]):
                parcial_hecho = True
                sl_actual = entry
                hitos.append(("partial", t, precio))
            if parcial_hecho:
                nuevo_sl = precio + TRAIL_STEP
                if nuevo_sl < sl_actual:
                    sl_actual = nuevo_sl
                if precio >= sl_actual:
                    salida = "TRAIL"
                    r_final = (entry - sl_actual) / risk
                    hitos.append(("trail_out", t, precio)); break

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
    from londonbos_core.storage import record_event

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
    record_event(
        db,
        "PAPER_TRADE_COMPLETED",
        session_date=fecha,
        direction=res.get("direccion"),
        price=res.get("entry"),
        r_multiple=res.get("r"),
        source="paper_trade",
        metadata={
            "exit": res.get("salida"),
            "take_profit": res.get("tp"),
            "stop_loss": res.get("sl"),
            "milestones": [h[0] for h in res.get("hitos", [])],
        },
    )


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
            "TRAIL": "🟡 TRAIL", "ABIERTA_11H": "⏳ Abierta al corte",
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
