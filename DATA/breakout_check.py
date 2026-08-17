"""Módulo · Breakout check (2:20 Lima, 20 min post-apertura Londres).

Consulta el precio actual de EUR/USD vía IB Gateway y compara contra los
niveles del box asiático de hoy (entry Buy/Sell Stop, SL, TP a 1.5R) para
determinar el estado del trade a los 20 minutos de la apertura de Londres.

Uso:
  DATA/.venv/bin/python DATA/breakout_check.py [--port 4001] [--client N] [--date YYYY-MM-DD]

Requiere IB Gateway conectado (lectura basta). Envía el reporte por Telegram
vía notifier.Notificador si hay token configurado.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notifier import Notificador, mensaje_box
from londonbos_core.models import Direction, SessionBox, StrategyConfig, TradeStatus
from londonbos_core.rules import evaluate_breakout

# ---- zonas horarias ----
LIMA = timezone(timedelta(hours=-5))
MARGIN = 0.00002  # buffer de 2 pips para entradas


def _ib_precio(port=4001, client=5):
    """Precio actual de EUR/USD vía IB (solo lectura basta)."""
    try:
        from ib_insync import IB, Forex
        ib = IB()
        ib.connect("127.0.0.1", port, clientId=client, timeout=8)
        contract = Forex("EURUSD")
        tick = ib.reqMktData(contract, "", False, False)
        ib.sleep(3)
        price = tick.last or tick.close
        ib.disconnect()
        return float(price) if price else None
    except Exception as e:
        print(f"[BREAKOUT] No se pudo leer precio IB: {e}")
        return None


def _box_hoy(port=4001, client=5, fecha=None):
    """Recalcula el box y conserva el contrato dict de fx_session."""
    try:
        import fx_session as fx
        box = fx.calcular_box(port=port, client=client, fecha_ref=fecha)
        return box if box else None
    except Exception as e:
        print(f"[BREAKOUT] No se pudo calcular box: {e}")
        return None


def evaluar(precio, box):
    """Determina el estado usando el motor de dominio compartido."""
    session = SessionBox(
        session_date=str(box["inicio"].date()),
        start=box["inicio"],
        end=box["fin"],
        high=box["maximo"],
        low=box["minimo"],
        bars=box.get("nbarras", 0),
        source=box.get("source", "unknown"),
    )
    snapshot = evaluate_breakout(precio, session, StrategyConfig())
    if snapshot.status is TradeStatus.NO_OPERABLE:
        return f"🔴 NO OPERABLE\nRango {session.range_pips:.1f} pips fuera de 15–40."
    if snapshot.status is TradeStatus.NO_BREAKOUT:
        return (f"⚪ SIN BREAKOUT\nEl precio {precio:.5f} sigue dentro del box "
                f"[{session.low:.5f} – {session.high:.5f}]. No se activó ninguna orden.")
    direction = snapshot.direction.value if snapshot.direction else "—"
    r = snapshot.r_multiple if snapshot.r_multiple is not None else 0.0
    if snapshot.status is TradeStatus.CLOSED and r > 0:
        return f"✅ TP ALCANZADO (+1.5R)\n{direction} cerrada en objetivo."
    if snapshot.status is TradeStatus.CLOSED and r < 0:
        return f"❌ SL GOLPEADO (-1.0R)\n{direction} cerrada en stop."
    return f"🔵 ABIERTA · {direction}\nPrecio {precio:.5f} ({r:+.2f}R)."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--client", type=int, default=5)
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-send", action="store_true",
                    help="No enviar por Telegram, solo imprimir.")
    args = ap.parse_args()

    box = _box_hoy(port=args.port, client=args.client, fecha=args.date)
    if not box:
        print("[BREAKOUT] Sin box, aborto.")
        return
    precio = _ib_precio(port=args.port, client=args.client + 1)
    if precio is None:
        print("[BREAKOUT] Sin precio IB, aborto.")
        return
    estado = evaluar(precio, box)
    fecha = (box["inicio"] or datetime.now(LIMA)).strftime("%Y-%m-%d")
    msg = (f"⏱ <b>London BOS · Breakout 20min</b> · {fecha}\n"
           f"📍 Precio actual: <b>{precio:.5f}</b>\n\n"
           f"{estado}\n\n"
           f"Box: techo {box['maximo']:.5f} · piso {box['minimo']:.5f} · "
           f"rango {box['rango']:.1f} pips")
    print(msg)
    if not args.no_send:
        n = Notificador()
        if n.ok:
            n.enviar(msg)
        else:
            print("[BREAKOUT] Notificador sin token — no enviado.")


if __name__ == "__main__":
    main()
