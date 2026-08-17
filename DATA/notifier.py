"""Módulo 6 · Notificador Telegram para London-BOS.

Envía alertas a Telegram cuando ocurren eventos:
  - box matutino (al generar dashboard)
  - breakout detectado
  - break-even alcanzado (+1R)
  - salida parcial (+2R)
  - cierre de operación

Uso:
  from notifier import Notificador
  n = Notificador(token=..., chat_id=...)
  n.enviar("📊 London BOS ... mensaje ...")

El token y chat_id se toman de variables de entorno LONDONBOS_TG_TOKEN y
LONDONBOS_TG_CHAT, o se pasan por argumento.
"""
import os
import urllib.request
import json


class Notificador:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.environ.get("LONDONBOS_TG_TOKEN")
        self.chat_id = chat_id or os.environ.get("LONDONBOS_TG_CHAT")
        self.ok = bool(self.token and self.chat_id)

    def enviar(self, texto):
        if not self.ok:
            print("[NOTIF] Sin token/chat configurado — no se envía.")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = json.dumps({"chat_id": self.chat_id, "text": texto,
                           "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read().decode("utf-8"))
            if resp.get("ok"):
                print("[NOTIF] Mensaje enviado.")
                return True
            print(f"[NOTIF] Error Telegram: {resp}")
            return False
        except Exception as e:
            print(f"[NOTIF] No se pudo enviar: {e}")
            return False


def mensaje_box(fecha, maximo, minimo, rango, operable):
    estado = "🟢 OPERABLE" if operable else "🔴 NO OPERAR"
    filtro = "DENTRO DE RANGO" if operable else "FUERA DE RANGO"
    return (f"📊 <b>London BOS</b> · {fecha}\n"
            f"{estado} · Box EUR/USD\n"
            f"Techo {maximo:.5f} · Piso {minimo:.5f}\n"
            f"Rango <b>{rango:.1f} pips</b>\n"
            f"Filtro 15-40: {filtro}")


if __name__ == "__main__":
    n = Notificador()
    n.enviar(mensaje_box("2026-07-16", 1.14523, 1.14346, 17.7, True))
