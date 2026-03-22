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


app = Flask(__name__)

# ===============================
# COORDENADAS CASA
# ===============================
HOME_LAT = 41.3563003
HOME_LON = 2.0291016

# ===============================
# VARIABLES
# ===============================
jugadores = []
juego_en_curso = False
dron = None
dron_lock = threading.Lock()

GEOFENCE_BUFFER_M = 2  # 2 m

"""
def safe_goto(d, lat, lon, alt, timeout_s=90):
    finished = threading.Event()
    result = {"ok": False, "err": None}

    def _run():
        try:
            d.goto(lat, lon, alt)
            result["ok"] = True
        except Exception as e:
            result["err"] = e
        finally:
            finished.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    if not finished.wait(timeout_s):
        print(f"TIMEOUT en goto({lat}, {lon}, {alt}) tras {timeout_s}s (posible espera infinita en dronLink)")
        return False

    if result["err"] is not None:
        print(f"Error en goto({lat}, {lon}, {alt}): {result['err']}")
        return False

    return True
"""

#LÓGICA PARA HTTP, AHORA SE HACE CON MQTT POR LO QUE NO SIRVE
"""
# ===============================
# CONEXIÓN DRON HTTP
# ===============================
def conectar_dron(tipo):
    global dron
    if dron is not None:
        return dron

    print("Conectando con el dron...")
    dron = Dron()
    if tipo == "Simulacion":
        dron.connect("tcp:127.0.0.1:5763", 115200)
    else:
        dron.connect("COM3", 57600)
    print("Dron conectado")
    return dron


@app.route("/connection", methods=["POST"])
def probar_conexion():
    try:
        data = request.json
        tipo = data.get('tipo')
        d = conectar_dron(tipo)
        return jsonify({"ok": True, "connected": d is not None}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


#======================================================
# ENDPOINT DESCONECTAR
#======================================================

def desconectar_dron():
    global dron
    if dron is None:
        print("No hay dron inicializado.")
        return False

    print("Desconectando el dron...")
    ok = dron.disconnect()
    print("Dron desconectado" if ok else "No se pudo desconectar (estado no permitido)")
    return ok

@app.route("/disconnection", methods=["POST"])
def disconnection():
    try:
        ok = desconectar_dron()
        return jsonify({"ok": True, "disconnected": ok}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ======================================================
# DESPEGAR
# ======================================================
def despegar_dron(h):
    global dron
    if dron is None:
        return False, "Dron no conectado (no hay instancia)."

    if getattr(dron, "state", None) != "connected":
        return False, f"Dron no está en estado 'connected' (estado actual: {getattr(dron,'state',None)})."

    try:
        dron.arm()
        dron.takeOff(h)
        return True, None
    except Exception as e:
        return False, str(e)


@app.route("/despegue", methods=["POST"])
def despegue():
    try:
        data = request.get_json(silent=True) or {}
        h = int(data.get("h", 5))
        ok, err = despegar_dron(h)
        if ok:
            return jsonify({"ok": True, "despegue": True}), 200
        else:
            return jsonify({"ok": False, "error": err}), 409
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ========================================================
# LAND
# ========================================================

@app.route("/land", methods=["POST"])
def land():
    global dron

    try:
        if dron is None:
            return jsonify({
                "ok": False,
                "error": "No hay instancia de dron."
            }), 409

        if getattr(dron, "state", None) not in ("flying", "armed"):
            return jsonify({
                "ok": False,
                "error": f"No se puede hacer land desde estado {getattr(dron,'state',None)}"
            }), 409

        dron.Land()
        return jsonify({"ok": True, "land": True}), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

# ========================================================
# GOTO
# ========================================================

@app.route("/GoTo", methods=["POST"])
def gotoAdmin():
    global dron

    try:
        if dron is None:
            return jsonify({"ok": False, "error": "No hay instancia de dron."}), 409

        if getattr(dron, "state", None) != "flying":
            return jsonify({
                "ok": False,
                "error": f"No se puede hacer goto si no está volando (estado: {getattr(dron,'state',None)})"
            }), 409

        data = request.get_json(silent=True) or {}
        if not all(k in data for k in ("lat", "lon", "h")):
            return jsonify({
                "ok": False,
                "error": "Faltan parámetros: lat, lon, h"
            }), 400

        lat = float(data["lat"])
        lon = float(data["lon"])
        alt = float(data["h"])

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return jsonify({"ok": False, "error": "lat/lon fuera de rango"}), 400
        if alt <= 0:
            return jsonify({"ok": False, "error": "h debe ser > 0"}), 400

        dron.goto(lat, lon, alt)
        return jsonify({"ok": True, "goto": True}), 200

    except ValueError:
        return jsonify({"ok": False, "error": "lat/lon/h deben ser numéricos"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500"""



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
    global dron
    with dron_lock:
        if dron is None:
            return True, None
        ok = bool(dron.disconnect())
        dron = None
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
    with dron_lock:
        if dron is None:
            return False, "No hay instancia de dron."

        if getattr(dron, "state", None) != "flying":
            return False, f"No se puede hacer goto si no está volando (estado: {getattr(dron,'state',None)})"


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

        else:
            print(f"Topic no reconocido: {topic}")

    except Exception as e:
        print(f"Error procesando topic {topic}: {e}")






"""
# ===============================
# CÁLCULO DE HEADING ABSOLUTO
# ===============================
def calcular_heading(origen_lat, origen_lon, destino_lat, destino_lon):
    d_lon = math.radians(destino_lon - origen_lon)
    lat1 = math.radians(origen_lat)
    lat2 = math.radians(destino_lat)

    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)

    heading = math.degrees(math.atan2(x, y))
    return (heading + 360) % 360


def seleccionar_objetivo_reciente(jugadores):
    jugadores_con_ts = [j for j in jugadores if isinstance(j.get("ts"), (int, float))]
    if jugadores_con_ts:
        return max(jugadores_con_ts, key=lambda j: j.get("ts", 0))
    return jugadores[-1]


# ===============================
# GEOFENCE DESDE EL DRON
# ===============================
def obtener_fence_inclusion(d):
    try:
        scenario = d.getScenario(blocking=True)
    except Exception as e:
        print("⚠️ No se pudo obtener scenario:", e)
        return None

    if not scenario or not isinstance(scenario, list) or len(scenario) == 0:
        return None

    # el primero es el fence de inclusión
    return scenario[0]


def clamp_objetivo_a_fence(lat, lon, fence):
    if not fence:
        return lat, lon

    if fence["type"] == "polygon":
        # aproximación: usamos el bounding box del polígono
        lats = [wp["lat"] for wp in fence["waypoints"]]
        lons = [wp["lon"] for wp in fence["waypoints"]]

        min_lat = min(lats)
        max_lat = max(lats)
        min_lon = min(lons)
        max_lon = max(lons)

        # margen en grados
        lat_margin = GEOFENCE_BUFFER_M / 111_111.0
        lon_margin = GEOFENCE_BUFFER_M / (111_111.0 * math.cos(math.radians(lat)))

        min_lat += lat_margin
        max_lat -= lat_margin
        min_lon += lon_margin
        max_lon -= lon_margin

        clamped_lat = max(min_lat, min(max_lat, lat))
        clamped_lon = max(min_lon, min(max_lon, lon))
        return clamped_lat, clamped_lon

    if fence["type"] == "circle":
        # clamp al radio - buffer
        center_lat = fence["lat"]
        center_lon = fence["lon"]
        radius_m = float(fence["radius"]) - GEOFENCE_BUFFER_M

        # distancia actual
        d_m = haversine_m(center_lat, center_lon, lat, lon)
        if d_m <= radius_m:
            return lat, lon

        # mover punto hacia el centro en el borde permitido
        bearing = calcular_bearing(center_lat, center_lon, lat, lon)
        return punto_a_distancia(center_lat, center_lon, bearing, radius_m)

    return lat, lon


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    to_rad = lambda x: x * math.pi / 180
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def calcular_bearing(lat1, lon1, lat2, lon2):
    d_lon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360) % 360


def punto_a_distancia(lat, lon, bearing_deg, dist_m):
    R = 6371000
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(math.sin(lat1) * math.cos(dist_m / R) +
                     math.cos(lat1) * math.sin(dist_m / R) * math.cos(brng))
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(dist_m / R) * math.cos(lat1),
        math.cos(dist_m / R) - math.sin(lat1) * math.sin(lat2)
    )

    return math.degrees(lat2), math.degrees(lon2)


# ===============================
# IR A UN OBJETIVO
# ===============================
def ejecutar_ir_a_objetivo(lat, lon):
    global juego_en_curso

    try:
        d = conectar_dron()

        print("Armando dron...")
        d.arm()

        print("Despegando...")
        d.takeOff(5)
        time.sleep(5)

        # ----------------------------
        # GEOFENCE (20 cm antes del límite)
        # ----------------------------
        fence = obtener_fence_inclusion(d)
        target_lat, target_lon = clamp_objetivo_a_fence(lat, lon, fence)

        print(f"Yendo al objetivo ({target_lat}, {target_lon})")
        ok = safe_goto(d, target_lat, target_lon, 5, timeout_s=120)

        if not ok:
            print("No se confirmó llegada al objetivo (timeout/error). Continúo con el flujo para no bloquear.")
        else:
            print("Estoy en el objetivo")

        time.sleep(5)

        # ----------------------------
        # GIRAR HACIA EL JUGADOR
        # ----------------------------
        heading = calcular_heading(
            origen_lat=HOME_LAT,
            origen_lon=HOME_LON,
            destino_lat=target_lat,
            destino_lon=target_lon
        )

        print(f"Girando dron a heading {heading:.1f}°")
        # d.changeHeading(heading)

        print("Cámara orientada al jugador")
        time.sleep(5)

        # ----------------------------
        # VOLVER A CASA
        # ----------------------------
        print("Volviendo a casa")

        ok_home = safe_goto(d, HOME_LAT, HOME_LON, 5, timeout_s=180)
        if not ok_home:
            print("No se confirmó regreso a casa. Intento RTL si está disponible.")
            try:
                if hasattr(d, "RTL"):
                    d.RTL(blocking=True)
            except Exception as e:
                print("RTL falló:", e)

        time.sleep(5)

        print("Aterrizando")
        try:
            d.Land()
        except Exception as e:
            print("⚠️ Land falló:", e)

        print("Juego completado")

    except Exception as e:
        print("Error durante ejecución:", e)

    finally:
        juego_en_curso = False


# ===============================
# REGISTRO DE JUGADOR
# ===============================
@app.route("/jugador", methods=["POST"])
def registrar_jugador():
    data = request.get_json() or {}
    print("jugador", data)

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    for j in jugadores:
        if j.get("alias") == alias:
            j["lat"] = lat
            j["lon"] = lon
            print(f"Jugador actualizado → {alias} ({lat}, {lon})")
            return jsonify({"status": "ok"}), 200

    jugadores.append({"lat": lat, "lon": lon, "alias": alias})
    print(f"Jugador registrado → {alias} ({lat}, {lon})")
    return jsonify({"status": "ok"}), 200


# ===============================
# UBICACIÓN EN DIRECTO (LIVE)
# ===============================
@app.route("/ubicacion-live", methods=["POST"])
def ubicacion_live():
    data = request.get_json() or {}
    
    print("jugadores", data)

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")
    precision = data.get("precision")
    ts = data.get("ts")

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    for j in jugadores:
        if j.get("alias") == alias:
            j["lat"] = lat
            j["lon"] = lon
            j["precision"] = precision
            j["ts"] = ts
            return jsonify({"status": "ok"}), 200

    jugadores.append({"lat": lat, "lon": lon, "alias": alias, "precision": precision, "ts": ts})
    return jsonify({"status": "ok"}), 200


# ===============================
# INICIAR JUEGO
# ===============================
@app.route("/iniciar-juego", methods=["POST"])
def iniciar_juego():
    global juego_en_curso, jugadores

    if juego_en_curso:
        print("juego en curso")
        return jsonify({"error": "Juego en curso"}), 400

    data = request.get_json(silent=True) or {}
    if isinstance(data.get("jugadores"), list) and data["jugadores"]:
        jugadores = data["jugadores"]
        print(f"Snapshot recibido: {len(jugadores)} jugadores")

    if not jugadores:
        print("no hay jugadores")
        return jsonify({"error": "No hay jugadores"}), 400

    juego_en_curso = True
    print("juego empezado")
    objetivo = seleccionar_objetivo_reciente(jugadores)
    print("tengo un objetivo")

    threading.Thread(
        target=ejecutar_ir_a_objetivo,
        args=(objetivo["lat"], objetivo["lon"]),
        daemon=True
    ).start()

    return jsonify({
        "status": "juego iniciado",
        "objetivo": objetivo["alias"]
    }), 200


# ===============================
# LAND (ADMIN)
# ===============================
#@app.route("/land", methods=["POST"])
#def land():
    #try:
     #   d = conectar_dron()
      #  d.Land()
       # return jsonify({"status": "ok"}), 200
    #except Exception as e:
     #   return jsonify({"error": str(e)}), 500


# ===============================
# RESET
# ===============================
@app.route("/reset", methods=["POST"])
def reset():
    global jugadores, juego_en_curso, dron

    jugadores = []
    juego_en_curso = False

    try:
        if dron:
            dron.Land()
            dron.disconnect()
    except:
        pass

    dron = None
    return jsonify({"status": "reset ok"}), 200
"""

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
