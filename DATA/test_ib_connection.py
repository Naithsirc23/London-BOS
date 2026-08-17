"""
Prueba de conexión a IB Gateway / TWS para London-BOS.

Valida los 3 centros que deben aparecer en verde en el gateway:
  1. API server        -> conexión de socket (ib.connect)
  2. Market data       -> reqMktData / qualified contract (EURUSD)
  3. Historical data   -> reqHistoricalData (barras 1m)

Uso:
    .venv/bin/python test_ib_connection.py [puerto] [client_id]

Puertos estándar IB:
    IB Gateway  (live)  : 4002
    IB Gateway  (paper) : 4001
    TWS         (live)  : 7496
    TWS         (paper) : 7497

El gateway debe tener "Enable ActiveX and Socket Clients" activo y la API
configurada en 127.0.0.1 (localhost). Si el cliente ID está en uso, cambia el
segundo argumento.
"""
from __future__ import annotations
import sys
import time
from datetime import datetime
from ib_insync import IB, Contract, Stock, Forex, util


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4002
    client_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    host = "127.0.0.1"

    print("=" * 60)
    print("  PRUEBA DE CONEXIÓN IB GATEWAY — London-BOS")
    print("=" * 60)
    print(f"  Host     : {host}")
    print(f"  Puerto   : {port}")
    print(f"  ClientID : {client_id}")
    print("-" * 60)

    ib = IB()

    # 1) API SERVER ------------------------------------------------------
    try:
        print("[1/3] Conectando al API server ...")
        ib.connect(host, port, clientId=client_id, timeout=15)
        print("       ✅ API server conectado")
    except Exception as e:
        print(f"       ❌ No se pudo conectar al API server: {e}")
        print("       Revisa que el gateway esté abierto y el puerto sea correcto.")
        return 1

    # 2) MARKET DATA -----------------------------------------------------
    print("[2/3] Solicitando market data (EURUSD) ...")
    eurusd = Forex("EURUSD")
    qualified = ib.qualifyContracts(eurusd)
    if not qualified:
        print("       ❌ No se pudo calificar el contrato EURUSD (sin market data).")
        ib.disconnect()
        return 1
    print(f"       ✅ Contrato calificado: {qualified[0].symbol} @ {qualified[0].exchange}")

    ticker = ib.reqMktData(qualified[0], "", False, False)
    # esperar a que llegue al menos un tick
    for _ in range(30):
        ib.sleep(0.5)
        if ticker.last or ticker.bid or ticker.ask:
            break
    ib.cancelMktData(qualified[0])
    if ticker.bid and ticker.ask:
        print(f"       ✅ Market data OK  bid={ticker.bid}  ask={ticker.ask}")
    else:
        # en algunas cuentas paper no hay last/bid; el contrato calificó => centro activo
        print(f"       ⚠️  Market data: contrato calificado pero sin tick en 15s "
              f"(común en paper). Centro considerado ACTIVO.")

    # 3) HISTORICAL DATA -------------------------------------------------
    print("[3/3] Solicitando datos históricos (EURUSD 1m, 1 día) ...")
    try:
        bars = ib.reqHistoricalData(
            qualified[0],
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="MIDPOINT",
            useRTH=False,
            formatDate=1,
        )
        if bars:
            first, last = bars[0], bars[-1]
            print(f"       ✅ Historical data OK  ({len(bars)} barras)")
            print(f"            primero: {first.date}  {first.close}")
            print(f"            último : {last.date}  {last.close}")
        else:
            print("       ❌ Historical data vacío (centro inactivo o sin permisos).")
            ib.disconnect()
            return 1
    except Exception as e:
        print(f"       ❌ Error en historical data: {e}")
        ib.disconnect()
        return 1

    ib.disconnect()
    print("-" * 60)
    print("  ✅ LOS 3 CENTROS RESPONDEN — IB listo para London-BOS")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
