# Validación visual de la integración de eventos

Fecha de validación: 2026-08-17.

Se abrió `index.html` localmente y se navegó al Módulo 7. El dashboard muestra el indicador `API: offline · vista local` cuando el navegador no puede acceder a la API, conserva el historial y paper trades preinyectados y presenta la nueva tarjeta `Eventos operativos` con columnas Fecha, Evento, Precio y R.

La conexión JavaScript está diseñada para usar `http://127.0.0.1:8080` al abrirse como `file://`, y para usar el mismo origen cuando se sirva por HTTP. La vista fallback funciona sin API y el refresco JSON queda preparado para reemplazar las tablas cuando el endpoint está disponible.


En el segundo pase se confirmó que el dashboard raíz carga el bloque nuevo sin errores de renderizado. La tarjeta de eventos y el indicador API están presentes; la vista conserva el fallback si la API local no está disponible. La conectividad dinámica requiere que el proceso Uvicorn esté activo y que el navegador permita la solicitud CORS desde `file://`.


Con la API reiniciada y CORS activo, el dashboard raíz mostró `API: read_only` y actualizó dinámicamente el historial y los paper trades. La tarjeta de eventos mostró `sin eventos` porque la base local todavía no contiene registros emitidos por una nueva ejecución de `fx_session.py` o `paper_trade.py`; el endpoint respondió correctamente y la UI manejó ese estado de forma explícita.
