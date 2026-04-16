import time
import random
import threading
import math
from flask import Flask, request, jsonify
from jinja2.filters import do_replace

from dronLink.Dron import Dron
import paho.mqtt.client as mqtt
import json


# =============================================================
# CONEXION MQTT
# =============================================================
BROKER_HOST = "broker.hivemq.com"
BROKER_PORT = 1883
TOPIC_SUB = "mobileFlask/demoDash/#"
TOPIC_TELEMETRY = "demoDash/mobileFlask/telemetryInfo"

TOPIC_CONNECT = "mobileFlask/demoDash/connect"
TOPIC_DISCONNECT = "mobileFlask/demoDash/diconnection"
TOPIC_TAKEOFF = "mobileFlask/demoDash/arm_takeOff"
TOPIC_LAND = "mobileFlask/demoDash/Land"
TOPIC_GOTO = "mobileFlask/demoDash/GoTo"
TOPIC_SET_GEOFENCE = "mobileFlask/demoDash/setGeofence"
TOPIC_GEOFENCE_POINTS = "mobileFlask/demoDash/geofencePoints"
current_geofence = None
TOPIC_SPEED = "mobileFlask/demoDash/speed"
TOPIC_CENTRARIMAGEN = "mobileFlask/demoDash/centrarimagen"
CENTER_IMAGE_MIN_SPEED = 0.1


app = Flask(__name__)

# ===============================
# VARIABLES
# ===============================
jugadores = []
juego_en_curso = False
dron = None
dron_lock = threading.Lock()
center_image_prev_speed = None

#GEOFENCE_BUFFER_M = 2  # 2 m

# ==============================================
# FUNCIÓN CONECTAR DRON MQTT
# ==============================================
def conectar_dron(tipo: str):
    global dron, mqtt_client

    with dron_lock:
        if dron is not None:
            return True, None

        print("voy a conectar", tipo)
        d = Dron()

        if tipo == "Simulacion":
            d.connect("tcp:127.0.0.1:5763", 115200, freq=1)
            print("Estoy conectado en modo simulacion")
        else:
            d.connect("COM3", 57600, freq=1)
            print("Estoy conectado al dron real")

        dron = d
        try:
            publicar_geofence()
            print("estoy publicando el geofence en conectar_dron")
        except Exception as e:
            print(f"Error publicando geofence inicial: {e}")

        try:
            dron.send_telemetry_info(procesar_telemetria)
            print("estoy publicando el geofence en conectar_dron")
            #print(f"Telemetría activada en {TOPIC_TELEMETRY}")
        except Exception as e:
            print(f"Error activando telemetría: {e}")


        return True, None


# ====================================================
# FUNCIÓN DESCONECTAR DRON MQTT
# ====================================================

def desconectar_dron():
    global dron, center_image_prev_speed
    with dron_lock:
        if dron is None:
            return True, None
        ok = bool(dron.disconnect())
        dron = None
        center_image_prev_speed = None
        print("Dron desconectado" if ok else "No se pudo desconectar")
        return ok, None

# ===============================================
# FUNCIÓN DESCONECTAR DRON MQTT
# ===============================================

def despegar_dron(h):
    print("Estoy intentando despegar")
    with dron_lock:
        if dron is None:
            return False, "Dron no conectado"

        if getattr(dron, "state", None) != "connected":
            return False, f"Estado inválido para despegar: {getattr(dron,'state',None)}."
        print("voy a armar")
        dron.arm()
        print("Voy a despegar")
        dron.takeOff(h)
        return True, None


# ================================================
# FUNCIÓN ATERRIZAR DRON MQTT
# ================================================

def land_dron():
    global center_image_prev_speed
    with dron_lock:
        if dron is None:
            return False, "No hay instancia de dron."

        if getattr(dron, "state", None) != "flying":
            return False, f"No se puede hacer goto si no está volando (estado: {getattr(dron,'state',None)})"


        center_image_prev_speed = None
        dron.Land()
        return True, None


# ==============================================
# FUNCIÓN GOTO DRON MQTT
# ==============================================

def goto_dron(lat, lon, h):
    with dron_lock:
        if dron is None:
            return False, "Dron no conectado"

        if getattr(dron, "state", None) != "flying":
            return False, f"No se puede hacer goto si no está volando (estado: {getattr(dron,'state',None)})"

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            print("Error h")
            return False, "lat/lon fuera de rango"
        if h <= 0:
            print("error h<0")
            return False, "h debe ser > 0"
        print("lat", lat, "lon", lon, "h", h)
        print("Estoy yendo a la ubicacion")
        dron.goto(lat, lon, h)
        #dron.goto(41.276429, 1.988627, 5)
        print("He acabado el primer goto")
        #dron.goto(41.2761472, 1.9883225, 5)
        return True, None
#conectar_dron("real")
#despegar_dron(5)
#goto_dron(41.276429, 1.988627, 5)

# ====================================================
# FUNCIÓN PARA OBTENER DATOS DE TELEMETRIA
# ===================================================

def procesar_telemetria(telemetry_info):
    try:
        payload = json.dumps(telemetry_info)
        mqtt_client.publish(TOPIC_TELEMETRY, payload)
        print("Telemetria enviada:", payload)
    except Exception as e:
        print("Error enviando telemetría:", str(e))

# ===============================
# GEOFENCE
# ===============================
def publicar_geofence():
    global dron, mqtt_client

    if dron is None or mqtt_client is None:
        print("No tengo ni dron ni mqtt_client")
        return
    print("Estoy cogiendo el escenario")
    scenario = dron.getScenario()
    print("tengo el escenario")

    if scenario is None:
        print("No hay geofence en el dron")
        return

    fence = scenario[0]

    if fence["type"] == "polygon":
        puntos = fence["waypoints"]
        print("geofence enviado", fence)
    else:
        puntos = [{
            "lat": fence["lat"],
            "lon": fence["lon"],
            "radius": fence["radius"]
        }]

    payload = json.dumps({"puntos": puntos})
    print("payload", payload)

    mqtt_client.publish(TOPIC_GEOFENCE_POINTS, payload)
    print("Geofence publicado:", payload)

def set_geofence_dron(puntos):
    global dron

    with dron_lock:
        if dron is None:
            return False, "Dron no conectado"

        waypoints = []
        for p in puntos:
            waypoints.append({
                "lat": float(p["lat"]),
                "lon": float(p["lon"])
            })

        scenario = [
            {
                "type": "polygon",
                "waypoints": waypoints
            }
        ]

        dron.setScenario(scenario)

    return True, None

#
# ===============================
# CHANGE SPEED
# ===============================
def setSpeed(speed):
    global dron

    with dron_lock:
        if dron is None:
            return False, "Dron no conectado"

        dron.changeNavSpeed(speed)
        return True, None


def centrarImagen(command):
    global dron, center_image_prev_speed

    normalized = str(command or "Stop").strip().capitalize()
    if normalized not in ("Left", "Right", "Stop"):
        return False, f"Comando de centrado no válido: {command}"

    with dron_lock:
        if dron is None:
            if normalized == "Stop":
                return True, None
            return False, "Dron no conectado"

        if normalized == "Stop":
            if getattr(dron, "going", False):
                dron.go("Stop")
            if center_image_prev_speed is not None:
                dron.changeNavSpeed(center_image_prev_speed)
                center_image_prev_speed = None
            return True, None

        if getattr(dron, "state", None) != "flying":
            return False, f"No se puede centrar si no está volando (estado: {getattr(dron,'state',None)})"

        current_speed = float(getattr(dron, "navSpeed", CENTER_IMAGE_MIN_SPEED) or CENTER_IMAGE_MIN_SPEED)
        if center_image_prev_speed is None and current_speed > CENTER_IMAGE_MIN_SPEED:
            center_image_prev_speed = current_speed

        if current_speed != CENTER_IMAGE_MIN_SPEED:
            dron.changeNavSpeed(CENTER_IMAGE_MIN_SPEED)

        dron.go(normalized)
        return True, None

# ===============================
# MQTT CALLBACKS
# ===============================
def on_connect(client, userdata, flags, rc):
    print(f"MQTT conectado, rc={rc}")
    client.subscribe(TOPIC_SUB)
    print(f"Suscrito a {TOPIC_SUB}")


# añade esto arriba
def run_async_action(name, fn, *args):
    def _job():
        try:
            ok, err = fn(*args)
            print(f"{name}: {'OK' if ok else err}")
        except Exception as e:
            print(f"{name} ERROR: {e}")
    threading.Thread(target=_job, daemon=True).start()


def on_message(client, userdata, msg):
    global mqtt_client
    mqtt_client = client

    topic = msg.topic
    payload = msg.payload.decode("utf-8").strip()

    try:
        if topic == TOPIC_CONNECT:
            tipo = payload if payload in ("Simulacion", "Real") else "Simulacion"
            run_async_action("CONNECT", conectar_dron, tipo)


        elif topic in (TOPIC_DISCONNECT, "mobileFlask/demoDash/disconnection"):
            run_async_action("DISCONNECT", desconectar_dron)

        elif topic == TOPIC_TAKEOFF:
            h = int(payload) if payload else 5
            run_async_action("TAKEOFF", despegar_dron, h)

        elif topic == TOPIC_LAND:
            run_async_action("LAND", land_dron)

        elif topic == TOPIC_GOTO:
            data = json.loads(payload or "{}")
            lat = float(data["lat"])
            lon = float(data["lon"])
            h = float(data["h"])
            run_async_action("GOTO", goto_dron, lat, lon, h)

        elif topic == TOPIC_SET_GEOFENCE:
            data = json.loads(payload or "{}")
            puntos = data["puntos"]
            run_async_action("SET_GEOFENCE", set_geofence_dron, puntos)

        elif topic == TOPIC_SPEED:
            data = json.loads(payload)
            if isinstance(data, dict):
                speed = float(data["speed"])
            else:
                speed = float(data)
            run_async_action("SPEED", setSpeed, speed)

        elif topic == TOPIC_CENTRARIMAGEN:
            run_async_action("CENTRAR_IMAGEN", centrarImagen, payload)

        else:
            print(f"Topic no reconocido: {topic}")

    except Exception as e:
        print(f"Error procesando topic {topic}: {e}")

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    mqtt_client.loop_start()

    print("Servidor Mission Planner arrancado")
    app.run(host="0.0.0.0", port=5002)
