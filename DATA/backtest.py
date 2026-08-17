"""
Backtest de la estrategia London-BOS sobre los ultimos ~7 dias.

Reglas implementadas:
  - Sesion asiatica: 19:00 (Lima) del dia anterior -> apertura de Londres
    (08:00 local de Londres, = 02:00 Lima en BST / 03:00 Lima en GMT).
  - Box: techo = max(High) asiatico, piso = min(Low) asiatico.
  - Filtro de operacion: rango en pips debe estar en [15, 40].
  - Entradas: buy stop = techo + 2 pips; sell stop = piso - 2 pips.
  - SL: lado opuesto del box (long -> piso; short -> techo).
  - Riesgo 2:1: TP = entrada +/- 2 * riesgo.
  - El breakout se determina por el primer stop cruzado en la sesion de Londres.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pytz

lima = pytz.timezone('America/Lima')
ldn = pytz.timezone('Europe/London')

BUFFER = 0.00020          # 2 pips
RANGE_MIN, RANGE_MAX = 15, 40
RR = 2.0                  # riesgo:recompensa 2:1

now = datetime.now(lima)
start_dt = now - timedelta(days=7)
end_dt = now + timedelta(days=1)

print(f"Descargando 1m EURUSD=X  {start_dt.date()} -> {end_dt.date()} ...")
data = yf.download("EURUSD=X",
                   start=start_dt.strftime('%Y-%m-%d'),
                   end=end_dt.strftime('%Y-%m-%d'),
                   interval="1m", auto_adjust=False, progress=False)
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.droplevel(1)
if data.index.tz is None:
    data.index = data.index.tz_localize("UTC")
data.index = data.index.tz_convert(lima)
print(f"Datos: {data.index.min()} -> {data.index.max()}  ({len(data)} barras)\n")

rows = []
for D in pd.date_range(start_dt.date() + timedelta(days=1), now.date()):
    D = D.date()
    # Ventana asiatica: D-1 19:00 Lima -> apertura Londres D 02:00/03:00 Lima
    asia_start = lima.localize(datetime(D.year, D.month, D.day)) - timedelta(hours=5)
    ldn_open = ldn.localize(datetime(D.year, D.month, D.day, 8, 0)).astimezone(lima)
    asia = data.loc[asia_start:ldn_open]
    if asia.empty:
        rows.append((D, None, "SIN DATOS ASIA", "", 0, 0, 0, 0, "skip"))
        continue

    top = float(asia['High'].max())
    bot = float(asia['Low'].min())
    rng = (top - bot) * 10000

    london_end = lima.localize(datetime(D.year, D.month, D.day, 21, 0))
    london = data.loc[ldn_open:london_end]
    if london.empty:
        rows.append((D, round(rng, 1), "SIN DATOS LONDRES", "", 0, 0, 0, 0, "skip"))
        continue

    if rng < RANGE_MIN or rng > RANGE_MAX:
        rows.append((D, round(rng, 1), "NO OPERAR (filtro)", "", 0, 0, 0, 0, "skip"))
        continue

    buy_stop = top + BUFFER
    sell_stop = bot - BUFFER
    up = london['High'] >= buy_stop
    dn = london['Low'] <= sell_stop
    if not up.any() and not dn.any():
        rows.append((D, round(rng, 1), "SIN BREAKOUT", "", 0, 0, 0, 0, "skip"))
        continue

    t_up = london.index[up][0] if up.any() else None
    t_dn = london.index[dn][0] if dn.any() else None

    if t_up is not None and (t_dn is None or t_up <= t_dn):
        direction = "LONG"
        entry = buy_stop
        sl = bot
        tp = entry + RR * (entry - sl)
        sub = london.loc[t_up:]
        hit_tp = sub['High'] >= tp
        hit_sl = sub['Low'] <= sl
    else:
        direction = "SHORT"
        entry = sell_stop
        sl = top
        tp = entry - RR * (sl - entry)
        sub = london.loc[t_dn:]
        hit_tp = sub['Low'] <= tp
        hit_sl = sub['High'] >= sl

    risk = abs(entry - sl) * 10000
    if hit_tp.any() and (not hit_sl.any() or sub.index[hit_tp][0] <= sub.index[hit_sl][0]):
        outcome = "TP"
        pnl = RR * risk
    elif hit_sl.any():
        outcome = "SL"
        pnl = -risk
    else:
        outcome = "OPEN"
        last_close = float(london['Close'].iloc[-1])
        pnl = (last_close - entry) * 10000 if direction == "LONG" else (entry - last_close) * 10000
        pnl = round(pnl, 1)

    rows.append((D, round(rng, 1), direction, outcome,
                 round(entry, 5), round(tp, 5), round(sl, 5),
                 round(risk, 1), round(pnl, 1)))

# Imprimir por dia
print(f"{'Fecha':<12}{'Rango':>7}  {'Dir':<5}{'Result':<6}{'Entry':>10}{'TP':>10}{'SL':>10}{'Riesgo':>8}{'PnL':>8}")
print("-" * 78)
decided = [r for r in rows if r[2] in ("LONG", "SHORT")]
for r in rows:
    D, rng, direction, outcome, entry, tp, sl, risk, pnl = r
    if direction in ("LONG", "SHORT"):
        print(f"{str(D):<12}{rng:>7}  {direction:<5}{outcome:<6}{entry:>10}{tp:>10}{sl:>10}{risk:>8}{pnl:>8}")
    else:
        print(f"{str(D):<12}{('' if rng is None else rng):>7}  {'':<5}{direction:<6}")

# Estadisticas
tp_trades = [r for r in decided if r[3] == "TP"]
sl_trades = [r for r in decided if r[3] == "SL"]
open_trades = [r for r in decided if r[3] == "OPEN"]
n = len(tp_trades) + len(sl_trades)
print("-" * 78)
print(f"Trades decididos : {n}  (TP={len(tp_trades)}, SL={len(sl_trades)}, OPEN={len(open_trades)})")
if n:
    wr = len(tp_trades) / n * 100
    avg_win = sum(r[8] for r in tp_trades) / len(tp_trades) if tp_trades else 0
    avg_loss = sum(r[8] for r in sl_trades) / len(sl_trades) if sl_trades else 0
    net = sum(r[8] for r in tp_trades + sl_trades)
    print(f"Win rate        : {wr:.1f}%")
    print(f"Avg win / loss  : {avg_win:.1f} / {avg_loss:.1f} pips")
    print(f"Net pips        : {net:+.1f}")
    pf = (sum(r[8] for r in tp_trades) / -sum(r[8] for r in sl_trades)) if sl_trades else float('inf')
    print(f"Profit factor   : {pf:.2f}" if pf != float('inf') else "Profit factor   : inf")
