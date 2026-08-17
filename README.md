# London BOS — London Breakout Strategy

## Resumen ejecutivo

Sistema modular de trading algorítmico basado en la estrategia London Breakout para el par EUR/USD en el mercado Forex. Construido en Python con visualización HTML por módulo.

Rendimiento histórico validado (backtest 10 años):
- Beneficio total: 301.1%
- Factor de beneficio: 1.39
- Drawdown máximo: 14.86%
- Tasa de acierto: 32% (ratio R:R alto)
- Muestra: 872 operaciones

## Cómo funciona

La sesión asiática (00:00–07:00 GMT / 07:00 PM–02:00 AM Lima) consolida el precio en un rango estrecho. Al abrir Londres (07:00 GMT / 02:00 AM Lima), el precio rompe ese rango con fuerza. La estrategia captura esa ruptura.

Filtro clave: solo se opera si el rango asiático está entre 15 y 40 pips.

## Arquitectura de módulos

| Módulo | Nombre | Estado | Descripción |
|--------|--------|--------|-------------|
| 1 | Reloj | ✅ Listo | Detecta sesiones, cuenta regresiva al disparo |
| 2 | Escáner | ✅ Listo (IB) | Extrae máx/mín asiático vía IB Gateway, calcula rango en pips |
| 3 | Filtro | ✅ Listo | Valida si el rango es operable (15–40 pips) |
| 4 | Órdenes | ✅ Listo | Calculadora Buy/Sell Stop con SL (modos Fijo/Manual/Trailing) |
| 5 | Gestor | ✅ Listo (simulador) | Break-even +1R, salida parcial +2R, trailing — simulador interactivo |
| 6 | Notificador | ✅ Listo (preview + motor) | Preview de mensajes + `DATA/notifier.py` listo para Telegram |
| 7 | Logger | ✅ Listo | SQLite `londonbos_log.db`; sesión de hoy se guarda al generar dashboard; tabla de sesiones (box + ruptura 20/60m) |
| 8 | Paper Trade | ✅ Listo | Simulación M5 minuto a minuto sobre barras 1m reales; evalúa ventana 02:00–11:00 (o `--hasta`); notifica resumen por TG |

## Stack técnico

- **IB Gateway / TWS API (ib_insync)** — fuente de datos real. Gateway corriendo en
  localhost de esta máquina.
  - Puerto validado: **4001** (paper, actualmente en **modo read-only** →
    `reqHistoricalData` devuelve Error 321; se usa **yfinance** como fallback).
  - ClientID: cualquiera libre (30+ usados por los crons).
  - `DATA/test_ib_connection.py` valida los 3 centros (API / market / historical).
- Telegram Bot dedicado (no reutiliza el bot de KRONOS): token en `DATA/.env`
  (`LONDONBOS_TG_TOKEN`) + chat `LONDONBOS_TG_CHAT=6091150597`.
- SQLite (logging: `sesiones` + `paper`).
- HTML/JS (SPA dashboard por módulo).

## Dashboard central (SPA)

`index.html` en la raíz es un **dashboard de una sola página (SPA)** que agrupa
los módulos 1–4 en un solo archivo. La barra de navegación superior cambia de
vista con botones (sin saltar a otros archivos), así funciona abierto desde
cualquier ubicación, incluido el adjunto de Telegram.

**Indicadores de fecha (todos los módulos):**
- **Barra de navegación (SPA):** muestra la fecha actual de Lima (`📅 DD/MM/AAAA`).
- **Cada módulo (SPA y sueltos):** badge **"Información de fecha"** con la fecha
  de los datos y tag **ACTUAL** (verde, ≤24h) o **DESFASADO** (rojo, >24h).
- M2, M4, M6, M7 (SPA) usan la **fecha real del box asiático** (inyectada por
  `fx_session.py` desde IB). M1, M3, M5 usan la fecha de hoy (en vivo).
- **Módulos sueltos M2 y M4:** también muestran la fecha real del box asiático
  (se inyecta al regenerar el dashboard). M1 y M3 son en vivo/interactivos.
- Sin fechas hardcodeadas: todo viene de IB vía `fx_session.py`.

Regenerar con datos reales (actualiza SPA + módulos sueltos M2/M4):
```bash
DATA/.venv/bin/python DATA/fx_session.py --html index.html
```
El widget de solo-box queda en `london-bos-ahora.html` (mismo comando, distinto path).

**Historial de sesiones (resuelto)**: al generar el dashboard, `fx_session.py`
guarda la sesión en `DATA/londonbos_log.db` (tabla `sesiones`). La vista M7 del
dashboard muestra las sesiones acumuladas (fecha, techo, piso, rango, operable).
Regenera cada mañana para ir poblando el historial. Próximo: selector de fecha
para revisar el box de cualquier día pasado directo en el dashboard.

EUR/USD — Forex vía IB (contrato `Forex("EURUSD")` en `IDEALPRO`).
Brokers alternativos evaluados: IC Markets / Pepperstone (MT5) — descartados por
límite de MT5 (win-only, requiere Wine) a favor de IB Gateway que ya conecta en verde.

## Estado de conexión IB (verificado 2026-07-19)

- IB Gateway conectado en verde: API server ✅, Market data center ✅,
  Historical data center ✅ (desde la UI del gateway).
- `fx_session.py` descarga barras 1m reales EURUSD vía **IB Gateway puerto 4001**
  (no usa yfinance fallback; el gateway funciona en modo paper con datos reales).
- Gateway en **modo read-only** (suficiente para datos; para ejecutar órdenes
  hay que desactivar read-only en el gateway).
- Puerto validado: **4001** (paper). ClientID: cualquiera libre (30+ usados por los crons).
- `DATA/test_ib_connection.py` valida los 3 centros (API / market / historical).
- Nota de arquitectura: el gateway corre en localhost de ESTA máquina Linux
  (puertos 4001/4002 abiertos localmente), no en el PC remoto del usuario.
- Autonomous: IB Gateway se mantiene vivo con `start-ibgateway.sh` (@reboot) +
  `watchdog.sh` (cada 5 min) en **crontab nativo** de Linux (no del scheduler de Hermes).
  El socket 4001 se abre solo en arranque fresco (limitación conocida IB+IBC);
  el watchdog hace cold-restart completo si cae.

## Horario Lima (GMT-5)

| Evento | GMT | Lima |
|--------|-----|------|
| Inicio sesión Asia | 00:00 | 07:00 PM |
| Cierre sesión Asia | 07:00 | 02:00 AM |
| Disparo estrategia | 07:00 | 02:00 AM |
| Solapamiento LDN+NY | 12:00–16:00 | 07:00–11:00 AM |

## Crons (crontab nativo Linux · America/Lima)

Los crons viven en el **crontab nativo** de la máquina (no en el scheduler de Hermes),
para que no dependan del agente. `crontab -l` muestra las entradas. Los scripts
están en `GITHUBS/London-BOS/cron/` con rutas absolutas. Todos usan **paper
trade evaluation** (ninguno es flash de un minuto):

| Cron | Hora Lima | Módulo | Qué hace |
|------|-----------|--------|----------|
| `@reboot` | — | start-ibgateway.sh | Levanta IB Gateway + IBC (xvfb-run) en 4001 |
| `*/5` | cada 5 min | watchdog.sh | Si 4001 cayó, cold-restart completo |
| `50 1 * * *` | 01:50 | armado.py | Box asiático + filtro 15-40 → "OPERABLE / NO OPERABLE" |
| `30 4 * * *` | 04:30 | paper_trade.py `--hasta 04:30` | Evalúa ventana 02:00–04:30 |
| `0 11 * * *` | 11:00 | paper_trade.py | Evalúa ventana completa 02:00–11:00 + R |

Nota: el antiguo `londonbos-breakout` (flash 2:20) se eliminó — su función la
absorbe `paper-mid`. `fx_session.py` regenera el dashboard (SPA + módulos
sueltos M2/M4) con la fecha real del box asiático cada vez que corre.

## Autor

Cris — CIR / Optima Nexus  
Proyecto parte del stack de automatización personal.
