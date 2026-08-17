"""Módulo · Armado de estrategia (1:50 Lima, ~10 min antes de Londres).

Calcula el box asiático del día, genera el dashboard y notifica por Telegram
la estrategia armada: niveles Buy/Sell Stop, SL y TP (1.5R).

Uso:
  DATA/.venv/bin/python DATA/armado.py [--port 4001] [--client N] [--date YYYY-MM-DD]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx_session as fx
from notifier import Notificador, mensaje_box

MARGIN = 0.00002  # 2 pips buffer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--client", type=int, default=1)
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--html", default="index.html")
    args = ap.parse_args()

    box = fx.calcular_box(port=args.port, client=args.client, fecha_ref=args.date)
    if not box:
        print("[ARMADO] Sin box, aborto.")
        return

    # generar dashboard
    fx._volcar_html(box["inicio"], box["fin"], box["maximo"], box["minimo"],
                    box["rango"], box["en_zona"], box["nbarras"],
                    args.html, central=True)

    mx, mn = box["maximo"], box["minimo"]
    fecha = box["inicio"].strftime("%Y-%m-%d")

    # ---- FILTRO DE OPERABILIDAD (decisión a la 1:50) ----
    if not box["en_zona"]:
        msg = (f"🔴 <b>London BOS · HOY NO OPERABLE</b> · {fecha}\n"
               f"📊 Box EUR/USD\nTecho {mx:.5f} · Piso {mn:.5f}\n"
               f"Rango <b>{box['rango']:.1f} pips</b>\n"
               f"Filtro 15–40: {'DEMASIADO ESTRECHO (<15)' if box['rango'] < 15 else 'DEMASIADO AMPLIO (>40)'}\n\n"
               f"⏸ Sin estrategia armada. No se opera hoy.")
        print(msg)
        if not args.no_send:
            n = Notificador()
            if n.ok:
                n.enviar(msg)
            else:
                print("[ARMADO] Notificador sin token — no enviado.")
        return

    # niveles 1.5R
    buy_entry = mx + MARGIN
    sell_entry = mn - MARGIN
    risk = abs(buy_entry - mn)
    tp_buy = buy_entry + 1.5 * risk
    tp_sell = sell_entry - 1.5 * risk

    msg = (f"🛠 <b>London BOS · Estrategia armada</b> · {fecha}\n"
           f"{mensaje_box(fecha, mx, mn, box['rango'], box['en_zona'])}\n\n"
           f"📌 <b>Niveles (RR 1.5:1)</b>\n"
           f"🔼 Buy Stop: <b>{buy_entry:.5f}</b>  SL {mn:.5f}  TP {tp_buy:.5f}\n"
           f"🔽 Sell Stop: <b>{sell_entry:.5f}</b>  SL {mx:.5f}  TP {tp_sell:.5f}\n\n"
           f"⏰ Disparo en apertura Londres (02:00 Lima). Reporte 2:20 AM.")
    print(msg)
    if not args.no_send:
        n = Notificador()
        if n.ok:
            n.enviar(msg)
        else:
            print("[ARMADO] Notificador sin token — no enviado.")


if __name__ == "__main__":
    main()
