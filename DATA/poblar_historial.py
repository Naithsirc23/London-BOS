"""Retro-puebla el logger con las últimas N sesiones asiáticas reales.

Consulta IB por cada fecha (hoy + N-1 previas), calcula el box y el veredicto,
y simula el breakout a 20 / 60 minutos post-apertura de Londres (02:00 Lima)
usando el precio real de EUR/USD en cada horizonte. Es la primera parte de un
backtest multi-horizonte.

Uso:
  DATA/.venv/bin/python DATA/poblar_historial.py [--dias 7] [--port 4001] [--client N]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx_session as fx
from breakout_check import evaluar, MARGIN

LIMA = timezone(timedelta(hours=-5))
HORIZONTES = [20, 60]  # minutos post-apertura (02:00 Lima); 120m eliminado (exagerado)


def precio_en(fecha_lima, port, client, minutos):
    """Precio de EUR/USD a las (02:00 + minutos) Lima de la fecha dada.
    Intenta IB; si falla (p.ej. gateway read-only), usa yfinance."""
    target = fecha_lima.replace(hour=2, minute=0, second=0, microsecond=0) \
        + timedelta(minutes=minutos)
    # 1) IB
    try:
        from ib_insync import IB, Forex
        fin = target + timedelta(minutes=2)
        ib = IB()
        ib.connect("127.0.0.1", port, clientId=client, timeout=10)
        contract = Forex("EURUSD")
        bars = ib.reqHistoricalData(contract, endDateTime=fin, durationStr="10 D",
                                     barSizeSetting="1 min", whatToShow="MIDPOINT",
                                     useRTH=False, formatDate=1)
        ib.disconnect()
        if bars:
            cand = [b for b in bars
                    if b.date.hour == target.hour and b.date.minute == target.minute
                    and b.date.date() == target.date()]
            return float((cand or bars)[-1].close)
    except Exception as e:
        print(f"  [precio {minutos}m] IB falló ({e}); probando yfinance...")
    # 2) yfinance fallback
    try:
        import yfinance as yf
        from datetime import time as dtime
        start = (target - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        end = (target + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        df = yf.download("EURUSD=X", start=start, end=end, interval="1m",
                         progress=False, auto_adjust=True)
        if df is not None and not df.empty:
            # la fila más cercana a target
            tloc = df.index.tz_convert("America/Lima") if df.index.tz else df.index
            best = min(tloc, key=lambda t: abs((t.hour*60+t.minute) - (target.hour*60+target.minute)))
            return float(df.loc[best, "Close"])
    except Exception as e:
        print(f"  [precio {minutos}m] yfinance error {fecha_lima.date()}: {e}")
    return None


def rupturas_para(fecha_lima, port, client):
    box = fx.calcular_box(port=port, client=client,
                          fecha_ref=fecha_lima.strftime("%Y-%m-%d"))
    if not box:
        return None, (None, None)
    res = []
    for k, mins in enumerate(HORIZONTES):
        precio = precio_en(fecha_lima, port, client + 10 + k, mins)
        if precio is None:
            res.append("⚪ sin datos")
        else:
            res.append(evaluar(precio, box).split("\n")[0])
        import time
        time.sleep(1.5)
    return box, tuple(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--client", type=int, default=1)
    args = ap.parse_args()

    import sqlite3
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "londonbos_log.db")
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS sesiones (
        fecha TEXT PRIMARY KEY, maximo REAL, minimo REAL,
        rango_pips REAL, operable INTEGER, barras INTEGER,
        generado TEXT, ruptura_20 TEXT, ruptura_60 TEXT)""")

    hoy = datetime.now(LIMA)
    for i in range(args.dias - 1, -1, -1):
        f = (hoy - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        fd = f.strftime("%Y-%m-%d")
        print(f"Procesando {fd}...")
        box, (r20, r60) = rupturas_para(f, args.port, args.client)
        if not box:
            print(f"  sin datos, skip")
            continue
        con.execute("""INSERT INTO sesiones (fecha, maximo, minimo, rango_pips,
            operable, barras, generado, ruptura_20, ruptura_60)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(fecha) DO UPDATE SET maximo=excluded.maximo,
            minimo=excluded.minimo, rango_pips=excluded.rango_pips,
            operable=excluded.operable, barras=excluded.barras,
            ruptura_20=excluded.ruptura_20, ruptura_60=excluded.ruptura_60""",
            (fd, box["maximo"], box["minimo"], box["rango"],
             1 if box["en_zona"] else 0, box["nbarras"],
             datetime.now(LIMA).strftime("%Y-%m-%d %H:%M:%S"),
             r20, r60))
        print(f"  -> rango {box['rango']:.1f}p operable={box['en_zona']} | "
              f"20m:{r20} | 60m:{r60}")
    con.commit()
    con.close()
    print("Listo. Logger poblado con horizontes 20/60/120.")


if __name__ == "__main__":
    main()
