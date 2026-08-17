# Roadmap London-BOS

Documento de estado y pendientes. Texto plano — no implementar todavía.
Última actualización: 2026-07-17.

## Origen de la estrategia
- Idea extraída de un reel de Instagram, pasado por Manus para sacar el contenido.
- El reel mencionaba un backtest de ~10 años con ~300% de ganancia (NO verificado: sin
  metodología, spreads, comisiones ni drawdown). Tratar como inspiración, no como hecho.
- Claude (en trabajo previo) indicó que para ser rentable necesitaba un ratio de riesgo
  2:1; luego acordamos que 1.5:1 también es viable y más alcanzable para EUR/USD.

## Módulos construidos (hasta ahora)
- `DATA/fx_session.py` — Módulo del rango asiático. Descarga EUR/USD 1m desde **IB
  Gateway** (`ib_insync` / `reqHistoricalData`, contrato `Forex("EURUSD")` en IDEALPRO),
  calcula el box asiático y muestra máximo, mínimo y rango en pips. yfinance queda como
  fallback (`--no-ib`). Parametrizable: `--date`, `--port`, `--client`. Venv en `DATA/.venv`.
- `DATA/backtest.py` — Backtester de la estrategia (PAUSADO). Reglas: box asiático, filtro
  15–40 pips, buffer 2 pips en entradas, SL en lado opuesto del box, RR 2:1 estático.
- `DATA/test_ib_connection.py` — **NUEVO (2026-07-17)**. Valida los 3 centros del IB
  Gateway (API / market data / historical). Verificado: ✅ los 3 responden en puerto 4001.

## Conexión de datos (VERIFICADO 2026-07-17)
- Pivote de broker: se descartó MT5 (win-only, requiere Wine) a favor de **IB Gateway**,
  que el usuario conectó en verde (API server / market data / historical data centers).
- El gateway corre en localhost de ESTA máquina Linux (puertos 4001/4002 abiertos).
- `test_ib_connection.py` descargó 1081 barras 1m reales EURUSD (2026-07-16→17) en puerto
  4001, ClientID 2. Contrato `Forex("EURUSD")` califica en `IDEALPRO`.
- Gateway en **modo solo lectura**: OK para datos; para ejecutar órdenes hay que
  desactivar read-only.
- Con `ib_insync` ya instalado en `DATA/.venv` (vía `uv pip install`), el backtest puede
  usar IB como fuente de histórico largo (resuelve la limitación de yfinance de 7 días).

## Lógica acordada
- Sesión asiática = rango de consolidación ANTES de la apertura de Londres.
  - Inicio: 19:00 Lima (apertura de Tokio, 09:00 JST).
  - Fin: apertura de Londres = 08:00 local de Londres → **02:00 Lima en verano (BST) /
    03:00 Lima en invierno (GMT)**. Lima no tiene DST; solo cambia el lado de Londres.
- Box: techo = max(High) asiático, piso = min(Low) asiático.
- Filtro de operación: rango en [15, 40] pips → operar; fuera de rango → no operar.
- Entradas (buffer 2 pips para evitar falsas activaciones):
  - buy stop = techo + 2 pips
  - sell stop = piso − 2 pips
- SL: lado opuesto del box (long → piso; short → techo).
- RR: 2:1 propuesto por Claude; 1.5:1 acordado como más alcanzable (ver hallazgos).
- Gestión de salida: NO estática. Debe incluir breakeven tras +1R, trailing y/o salida
  parcial. (Pendiente de definir y programar.)
- **Esquema de gestión de salida ACORDADO (2026-07-17), ver README/Módulo 5:**
  1. Activación: se llena la orden direccional; se cancela la opuesta.
  2. Break-even +1R: en +1.0R el SL sube a entry (sin pérdida).
  3. Salida parcial +2R: cierra 50% de la posición; SL a entry duro.
  4. Trailing 50% restante: SL sigue al precio cada 10 pips desde +2R hasta cierre.
  5. Cierre forzoso: 11:00 Lima (fin solapamiento LDN/NY) o hit de trailing.
  - Implementado como **simulador interactivo** en el dashboard SPA (vista M5).
    Falta: motor real conectado a IB (requiere gateway fuera de read-only).

## Hallazgos / validación real
- Bug corregido: yfinance 1.5.1 devuelve columnas MultiIndex → se aplanan con
  `data.columns.droplevel(1)`.
- La ventana asiática original (9h, hasta 04:00 Lima) estaba MAL para London-BOS: incluía
  2h de la sesión de Londres. Corregida a terminar en la apertura de Londres (7h → 02:00 Lima).
- Día real 2026-07-13: box techo 1.14116 / piso 1.13895 / rango 22.1 pips (en zona 15–40).
  Long en 1.14136, pico 1.14495 a las 03:18 Lima (+35.9 pips ≈ 1.49× riesgo), luego reversión
  y SL a las 11:31 en 1.13895 (−24.1 pips). El TP 2:1 (1.14618) NUNCA se tocó; el 1.5× (1.14498)
  se quedó a 0.25 pips. => 1.5:1 habría capturado el movimiento; 2:1 no.
- Backtest de 1 semana (05–13 jul, 8541 barras 1m): 2 trades decididos (ambos SL: −26.8 y
  −24.1), 2 OPEN flotando positivo (+17.6 y +12.4), 1 sin breakout. Inconcluso: muestra
  pequeña, el 2:1 no se alcanzó en ningún trade esa semana.
- Limitación de datos: yfinance solo da 1m para ~7 días. Para validar se necesita 15m/5m
  sobre meses.

## Pendientes (mapa de lo que falta corregir / implementar)
1. **Gestión de salida (lo más importante):** ✅ DISEÑO + SIMULADOR listo (2026-07-17,
   vista M5 del dashboard). Falta motor real IB (requiere gateway fuera de read-only).
2. **Parametrizar RR:** hacer 1.5:1 (y 2:1) configurables y comparar en backtest.
3. **Backtest serio:** cambiar a intervalo 15m/5m y correr meses para sacar win rate real,
   profit factor y expectancy; comparar 1:1 vs 1.5:1 vs 2:1.
4. **Cierre de sesión para trades OPEN:** definir qué pasa si no hay TP/SL (cerrar a fin de
   sesión, breakeven, etc.). El backtest actual los deja flotando.
5. **Módulo de breakout:** reglas exactas de entrada (¿solo en ventana post-apertura de
   Londres? ¿qué hacer si no hay breakout?).
6. **Decidir SL:** ¿piso del box o sell_stop (piso − 2 pips)? Ambos se usaron en pruebas.
7. **Parametrizar fecha en fx_session.py:** ✅ RESUELTO (2026-07-17) — usa HOY en Lima
   por defecto; `--date YYYY-MM-DD` para histórico.
8. **Validar el claim del reel** (10 años / 300%): mantener como hipótesis no verificada.
9. **Fuente de datos para histórico largo:** IB Gateway da histórico 1m/5m/15m, PERO
   el gateway actual está en **modo read-only** (Error 321 en `reqHistoricalData`),
   así que `poblar_historial.py` y `fx_session.py` usan **yfinance como fallback**
   (1m ~7 días). Para backtest de meses se necesita gateway fuera de read-only o
   otra fuente (CSV/Dukascopy).
10. **Adaptar fx_session.py y backtest.py a IB:** ✅ `fx_session.py` migrado a IB
    (2026-07-17) con fallback yfinance. Falta: migrar `backtest.py` para backtest largo.

## Notas
- El backtest está PAUSADO por petición del usuario (toma mucho tiempo). Retomar cuando se
  decida, idealmente ya con la gestión de salida (ítem 1) programada.
- **Módulos 4–7 COMPLETOS (2026-07-17):**
  - M4 Órdenes: calculadora Buy/Sell Stop (Fijo/Manual/Trailing), datos IB.
  - M5 Gestor: simulador interactivo BE+1R / parcial+2R / trailing (motor real IB
    pendiente: requiere gateway fuera de read-only).
  - M6 Notificador: preview de mensajes + `DATA/notifier.py` (clase `Notificador`)
    listo para Telegram vía `LONDONBOS_TG_TOKEN` / `LONDONBOS_TG_CHAT` (en `DATA/.env`).
    Bot dedicado creado por el usuario (no reusar el de KRONOS).
  - M7 Logger: `DATA/londonbos_log.db` (tabla `sesiones`); al generar dashboard se
    guarda la sesión del día. Histórico visible en vista M7. Resuelve el pedido de
    "historial de sesiones pasadas" (falta solo selector de fecha en el dashboard).

## Automatización (CRONS — 2026-07-17)

**Horarios fijos (Lima, UTC-5). Acordado: armar a 1:50 AM, revisar breakout a 2:20 AM.**
- `londonbos-armado` → `50 1 * * *` (1:50 Lima): corre `DATA/armado.py`, genera el
  dashboard con el box asiático del día y notifica por Telegram la estrategia armada
  (niveles Buy/Sell Stop + SL + TP **1.5:1**).
  **Filtro de operabilidad (2026-07-17, 03:xx):** si el rango NO está en 15–40 pips,
  el armado envía "🔴 HOY NO OPERABLE" y NO arma niveles ni opera. Decisión a la 1:50.
- `londonbos-breakout` → `20 2 * * *` (2:20 Lima): corre `DATA/breakout_check.py`,
  consulta el precio actual de EUR/USD vía IB y reporta el breakout a 20 min:
  TP alcanzado / SL golpeado / abierta (dirección + R según M5).
- Wrapper: `~/.hermes/scripts/londonbos-run.sh` (activa venv, carga `DATA/.env`,
  exporta `LONDONBOS_TG_CHAT`). Ambos crons `no_agent=true` (script puro, stdout a TG).
- **Pendiente verificar (invierno):** Londres en GMT (oct–mar) abre 01:00 Lima, por lo
  que el armado a 1:50 quedaría DESPUÉS de la apertura. Por ahora fijado a 1:50 por
  acuerdo explícito; en invierno hay que adelantar a ~00:50 o detectar BST/GMT.

## Backtest multi-horizonte (M7 · 2026-07-17)

El Logger (M7) ahora es la **primera fase del backtest**: por cada sesión asiática
guarda el box (max/min/rango/operable) y evalúa la ruptura a **20 / 60 minutos**
post-apertura de Londres (02:00 Lima) usando el precio real de EUR/USD en cada horizonte.
(El horizonte de 120 min se eliminó el 2026-07-17: el motor paper demostró que la
ruptura ocurre temprano y el 120m era una ilusión de medición por fotos aisladas.)

- `DATA/poblar_historial.py [--dias N]`: retro-puebla la DB con N sesiones. Para cada
  fecha consulta IB (fallback yfinance si gateway read-only) el precio a 02:20 / 03:00
  Lima y corre `breakout_check.evaluar()` → guarda `ruptura_20/60`.
- Tabla M7 muestra las 2 columnas de ruptura. Permite ver: ¿la ruptura ocurre a 20 o 60 min?
- **Hallazgo (motor paper, minuto a minuto):** la ruptura real ocurre a 10-30 min y es
  efímera (el precio revierte). Las fotos a 20/60 min dicen "sin breakout" porque miden
  precio sostenido, no cruce intradía. Por eso el motor paper (Opción B) es el veredicto real.
- Límite: yfinance solo 1m ~7 días → el backtest serio (meses, win rate, profit factor)
  requiere gateway fuera de read-only o CSV/Dukascopy (ítem 10).

## Ratio de riesgo (R:R)
- **Fijado en 1.5:1** (acordado con el usuario 2026-07-17). TP = entry + 1.5×riesgo.
  El trailing del M5 NO modifica este ratio: es técnica de salida post-+2R que mejora
  el R:R promedio real cuando hay tendencia, pero el TP de referencia sigue 1.5R.
- Valida mejor que 2:1 en datos reales del 13JUL (el 2:1 nunca se alcanzó; 1.5:1 sí).
- Convención de sesiones documentada también en los docstrings de `fx_session.py` y
  `backtest.py`.
