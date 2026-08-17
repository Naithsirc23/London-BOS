# Roadmap de implementación London-BOS

## Objetivo

Convertir London-BOS de un prototipo compuesto por HTML generado, scripts acoplados y datos locales en una plataforma modular de análisis y paper trading, manteniendo la ejecución real de órdenes desactivada hasta validar el dominio y la calidad histórica.

## Principios

La lógica de estrategia debe ser determinista y testeable. Las fuentes externas, la persistencia, las notificaciones y la interfaz deben depender de contratos de datos comunes, no al revés. Toda señal debe incluir fecha, zona horaria, fuente, antigüedad y versión de configuración. El dashboard debe ser de solo lectura mientras la validación estadística siga incompleta.

## Roadmap por fases

| Fase | Resultado esperado | Estado |
|---|---|---|
| 0. Seguridad y saneamiento | Secretos, DB y logs fuera de Git; `.env.example`; configuración local documentada. | **Iniciada** |
| 1. Dominio común | Contratos `SessionBox`, `TradePlan`, `BreakoutSnapshot`, `StrategyConfig` y reglas puras compartidas. | **Iniciada** |
| 2. Correcciones de consistencia | `breakout_check.py` consume el diccionario real de `calcular_box()`; el simulador comparte planes y RR. | **Completada** |
| 3. API de lectura | Endpoints JSON para health, sesión, historial, paper trades y eventos, con frescura y modo read-only. | **Completada** |
| 4. Dashboard por widgets | La SPA consulta JSON, refresca cada 30 segundos y muestra estado de API, historial, paper trades y eventos. | **Iniciada** |
| 5. Analítica | Equity curve, drawdown, expectancy, profit factor, distribución de R y gráficos por sesión. | Pendiente |
| 6. Datos históricos | Adaptador IB/CSV/Dukascopy con cache, normalización de timezone y backtest multi-mes. | Pendiente |
| 7. Operación robusta | Scheduler configurable, logs estructurados, alertas de salud, backups y recuperación. | Pendiente |
| 8. Ejecución real | Solo tras validación y controles explícitos de riesgo; requiere retirar read-only de IB. | Bloqueada por diseño |

## Primera iteración implementada

Se añadió `DATA/londonbos_core/` como capa de dominio sin dependencias de IB, SQLite, Telegram ni HTML. `StrategyConfig` centraliza los umbrales de rango, buffer, RR, trailing y hora de cierre. `SessionBox` representa el box asiático; `TradePlan` representa una operación; `evaluate_breakout()` resuelve el estado a partir de un precio; y `management_thresholds()` evita anunciar una salida parcial que no esté configurada.

Se corrigió el contrato de `breakout_check.py`: la función ahora consume el diccionario devuelto por `fx_session.calcular_box()` y delega la evaluación en el motor común. El simulador de `paper_trade.py` también construye sus niveles mediante el mismo motor y deja explícitamente desactivada la salida parcial mientras el TP de referencia sea 1.5R.

Se añadió `DATA/api.py`, una API de lectura con endpoints `/api/health`, `/api/session/latest`, `/api/session/history`, `/api/paper-trades` y `/api/events`. La API no coloca órdenes ni envía notificaciones.

## Criterios de aceptación siguientes

La siguiente iteración debe incorporar una tabla `trade_events`, definir una respuesta común de error y frescura de datos, añadir selección de fecha en el dashboard y sustituir la generación de tablas HTML por consumo JSON. El backtest debe compartir exactamente `StrategyConfig` y la misma máquina de estados que paper trade.

## Comandos locales

```bash
# Pruebas del dominio
PYTHONPATH=DATA python3 -m pytest -q tests/test_rules.py

# Verificación sintáctica
python3 -m py_compile DATA/api.py DATA/londonbos_core/*.py DATA/breakout_check.py DATA/paper_trade.py

# API local de solo lectura
PYTHONPATH=DATA uvicorn api:app --app-dir DATA --host 127.0.0.1 --port 8080
```

La API debe exponerse únicamente en `127.0.0.1` durante esta fase. No se deben activar órdenes reales ni publicar `DATA/.env`, `DATA/londonbos_log.db` o los logs operativos.

## Segunda iteración: eventos y conexión del dashboard

La tabla `trade_events` se crea de forma no destructiva junto con `schema_meta`, conserva timestamp, sesión, dirección, precio, R, fuente y metadata JSON, y cuenta con índices por timestamp y sesión. `fx_session.py` emite `SESSION_RECORDED` al registrar una sesión; `paper_trade.py` emite `PAPER_TRADE_COMPLETED` al guardar un resultado.

La SPA central y el `index.html` de raíz consumen `/api/health`, `/api/session/history`, `/api/paper-trades` y `/api/events`. El refresco ocurre cada 30 segundos, mantiene los datos HTML preinyectados como fallback y muestra claramente `read_only`, offline o última actualización. Los eventos aparecen en una línea temporal dentro del Módulo 7.

La siguiente mejora es conectar también eventos de `ARMED`, `BREAKOUT_DETECTED`, `BREAK_EVEN`, `PARTIAL` y `CLOSED` desde una máquina de estados única, además de añadir filtros de fecha y una API de métricas agregadas.
