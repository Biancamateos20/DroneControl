import math
import threading
import time

try:
    from DronLink.dronLink.Dron import Dron
except Exception:
    Dron = None

RADIO_TIERRA_M = 6371000.0

D = (41.276443, 1.988586)
USUARIOS = {
    "m1": (41.276380, 1.988146),
    "m2": (41.276568, 1.988428),
    "m3": (41.276304, 1.989122),
}

SCENARIO = [
    {
        "type": "polygon",
        "waypoints": [
            {"lat": 41.2764398, "lon": 1.9882585},
            {"lat": 41.2761999, "lon": 1.9883537},
            {"lat": 41.2763854, "lon": 1.9890994},
            {"lat": 41.2766273, "lon": 1.9889948},
        ],
    },
    {
        "type": "polygon",
        "waypoints": [
            {"lat": 41.2764801, "lon": 1.9886541},
            {"lat": 41.2764519, "lon": 1.9889626},
            {"lat": 41.2763995, "lon": 1.9887963},
        ],
    },
    {
        "type": "polygon",
        "waypoints": [
            {"lat": 41.2764035, "lon": 1.9883262},
            {"lat": 41.2762160, "lon": 1.9883537},
            {"lat": 41.2762281, "lon": 1.9884771},
        ],
    },
    {
        "type": "circle",
        "radius": 2,
        "lat": 41.2763430,
        "lon": 1.9883953,
    },
]

CONEXIONES = [
    #("tcp:127.0.0.1:5763", 115200),
    ("COM3", 57600),
]


def a_local(origen, punto):
    # Paso todo a coordenadas locales para trabajar en metros
    lat0, lon0 = map(math.radians, origen)
    lat, lon = map(math.radians, punto)
    # x sale de la diferencia de longitud, corregida por cos(lat)
    x = (lon - lon0) * RADIO_TIERRA_M * math.cos(lat0)
    # y sale directamente de la diferencia de latitud
    y = (lat - lat0) * RADIO_TIERRA_M
    return x, y


def a_global(origen, punto):
    lat0, lon0 = origen
    x, y = punto
    # Aqui hago la inversa para volver de metros a lat/lon
    lat = lat0 + math.degrees(y / RADIO_TIERRA_M)
    lon = lon0 + math.degrees(x / (RADIO_TIERRA_M * math.cos(math.radians(lat0))))
    return lat, lon


def distancia(a, b):
    return math.dist(a, b)


def distancia_lado(punto, a, b):
    # Distancia perpendicular con signo a la recta que pasa por ese lado
    return (
        (punto[0] - a[0]) * (b[1] - a[1]) - (punto[1] - a[1]) * (b[0] - a[0])
    ) / math.hypot(b[0] - a[0], b[1] - a[1])


def leer_posicion_dron(dron, espera=5):
    posicion = {"lat": None, "lon": None}
    recibida = threading.Event()

    def procesar_telemetria(telemetry_info):
        lat = telemetry_info.get("lat")
        lon = telemetry_info.get("lon")
        if lat or lon:
            posicion["lat"] = lat
            posicion["lon"] = lon
            recibida.set()

    dron.send_telemetry_info(procesar_telemetria)
    recibida.wait(espera)
    dron.stop_sending_telemetry_info()
    time.sleep(0.2)

    if posicion["lat"] is None or posicion["lon"] is None:
        return None

    return posicion["lat"], posicion["lon"]


def leer_escenario():
    if Dron is None:
        return SCENARIO, "scenario hardcodeado", None, D

    for conexion, baud in CONEXIONES:
        dron = Dron()
        escenario = None
        posicion = None
        try:
            dron.connect(conexion, baud, freq=10)
            time.sleep(1)

            for _ in range(3):
                escenario = dron.getScenario()
                if escenario:
                    posicion = leer_posicion_dron(dron)
                    if posicion is not None:
                        print(f"Estoy usando el geofence del dron en {conexion}")
                        print(f"Y tambien la posicion real del dron: {posicion}")
                        return escenario, f"geofence del dron ({conexion})", dron, posicion

                    print(f"He leido el geofence del dron en {conexion}, pero no ha llegado telemetria")
                    return escenario, f"geofence del dron ({conexion})", dron, D
                time.sleep(0.5)
        except Exception:
            pass
        finally:
            if not escenario:
                try:
                    dron.disconnect()
                except Exception:
                    pass

    # Si no hay dron disponible, tiro con el scenario que ya tenia puesto
    return SCENARIO, "scenario hardcodeado", None, D


def leer_usuario():
    while True:
        usuario = input("Elige usuario destino (m1, m2 o m3): ").strip().lower()
        if usuario in USUARIOS:
            return usuario
        print("Usuario no valido.")


def leer_margen():
    while True:
        try:
            return float(input("Metros antes del geofence para parar el dron: ").replace(",", "."))
        except ValueError:
            print("Introduce un numero valido.")


def quiere_ir_al_punto():
    respuesta = input("Quieres hacer goto al punto calculado y luego Land? (s/n): ").strip().lower()
    return respuesta in ["s", "si", "sí", "y", "yes"]


def dentro_poligono(punto, poligono):
    x, y = punto
    dentro = False

    for i in range(len(poligono)):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % len(poligono)]

        if (y1 > y) != (y2 > y):
            corte_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < corte_x:
                dentro = not dentro

    return dentro


def buscar_primer_corte(escenario, D, M):
    origen = (0.0, 0.0)
    destino = a_local(D, M)
    fence = escenario[0]
    epsilon = 1e-6

    if fence["type"] == "polygon":
        # El calculo se hace solo con el fence de inclusion
        poligono = [a_local(D, (wp["lat"], wp["lon"])) for wp in fence["waypoints"]]

        if not dentro_poligono(origen, poligono):
            raise ValueError("El dron D debe estar dentro del fence de inclusion.")

        dx = destino[0] - origen[0]
        dy = destino[1] - origen[1]
        cortes = []

        for i in range(len(poligono)):
            a = poligono[i]
            b = poligono[(i + 1) % len(poligono)]
            sx = b[0] - a[0]
            sy = b[1] - a[1]
            # Este denominador me dice si la trayectoria y el lado son paralelos o no
            den = dx * sy - dy * sx

            if abs(den) < 1e-9:
                continue

            qx = a[0] - origen[0]
            qy = a[1] - origen[1]
            # t es donde cae el corte sobre la trayectoria D -> M
            t = (qx * sy - qy * sx) / den
            # u es donde cae ese mismo corte dentro del lado del poligono
            u = (qx * dy - qy * dx) / den

            if epsilon < t <= 1.0 and 0.0 <= u <= 1.0:
                punto = (origen[0] + dx * t, origen[1] + dy * t)
                cortes.append(
                    {
                        "tipo": "inclusion_polygon",
                        "t": t,
                        "punto": punto,
                        "segmento": (a, b),
                    }
                )

        if not cortes:
            raise ValueError("La trayectoria D -> M no corta el geofence.")

        # Me quedo con el primer corte en la trayectoria
        return min(cortes, key=lambda corte: corte["t"]), destino

    if fence["type"] == "circle":
        centro = a_local(D, (fence["lat"], fence["lon"]))
        radio = fence["radius"]

        if distancia(origen, centro) > radio:
            raise ValueError("El dron D debe estar dentro del fence de inclusion.")

        dx = destino[0] - origen[0]
        dy = destino[1] - origen[1]
        ox = origen[0] - centro[0]
        oy = origen[1] - centro[1]

        # Aqui sale la interseccion entre la recta D->M y el circulo
        # Sale de meter la recta en la ecuacion del circulo y resolver la cuadratica
        aa = dx * dx + dy * dy
        bb = 2 * (ox * dx + oy * dy)
        cc = ox * ox + oy * oy - radio * radio
        disc = bb * bb - 4 * aa * cc

        if disc < 0:
            raise ValueError("La trayectoria D -> M no corta el geofence.")

        raiz = math.sqrt(disc)
        cortes = []
        for t in [(-bb - raiz) / (2 * aa), (-bb + raiz) / (2 * aa)]:
            if epsilon < t <= 1.0:
                punto = (origen[0] + dx * t, origen[1] + dy * t)
                cortes.append({"tipo": "inclusion_circle", "t": t, "punto": punto})

        if not cortes:
            raise ValueError("La trayectoria D -> M no corta el geofence.")

        return min(cortes, key=lambda corte: corte["t"]), destino

    raise ValueError("El primer fence debe ser un poligono o un circulo.")


def calculo(escenario, D, M, margen):
    if margen < 0:
        raise ValueError("La distancia de margen no puede ser negativa.")

    corte, destino = buscar_primer_corte(escenario, D, M)
    punto_fence = corte["punto"]
    distancia_fence = distancia((0.0, 0.0), punto_fence)

    if "segmento" not in corte:
        raise ValueError("Este calculo esta pensado para un fence poligonal.")

    a, b = corte["segmento"]
    distancia_dron_lado = abs(distancia_lado((0.0, 0.0), a, b))

    # Si el dron ya esta mas cerca del lado que el margen pedido, no hay punto valido antes del fence
    if margen > distancia_dron_lado:
        raise ValueError(
            f"El dron esta a {distancia_dron_lado:.2f} m de la arista; "
            f"no se puede parar a {margen:.2f} m de ella."
        )

    if distancia_dron_lado == 0:
        raise ValueError("El dron ya esta sobre la arista del geofence.")

    # La distancia perpendicular al lado baja de forma lineal hasta 0 en el corte
    t_parada = corte["t"] * (1 - margen / distancia_dron_lado)
    punto_parada = (destino[0] * t_parada, destino[1] * t_parada)
    distancia_p_lado = abs(distancia_lado(punto_parada, a, b))

    resultado = {
        "usuario": M,
        "p": a_global(D, punto_parada),
        "fence_mas_cercano": corte["tipo"],
        "distancia_desde_dron_al_fence_m": distancia_fence,
        "distancia_desde_p_al_fence_m": distancia_p_lado,
        "distancia_perpendicular_desde_dron_a_la_arista_m": distancia_dron_lado,
        "distancia_perpendicular_desde_p_a_la_arista_m": distancia_p_lado,
        "margen_solicitado_m": margen,
        "punto_fence": a_global(D, punto_fence),
    }

    resultado["segmento_fence"] = (a_global(D, a), a_global(D, b))

    return resultado


if __name__ == "__main__":
    usuario = leer_usuario()
    margen = leer_margen()
    escenario, origen, dron, posicion_dron = leer_escenario()
    resultado = calculo(escenario, posicion_dron, USUARIOS[usuario], margen)
    print(origen)
    print(f"Posicion usada del dron: lat={posicion_dron[0]}, lon={posicion_dron[1]}")
    print(resultado)

    if dron is not None and quiere_ir_al_punto():
        print("voy a armar")
        dron.arm()
        print("Voy a despegar")
        dron.takeOff(5)

        posicion_dron = leer_posicion_dron(dron)
        if posicion_dron is None:
            posicion_dron = D

        resultado = calculo(escenario, posicion_dron, USUARIOS[usuario], margen)
        lat, lon = resultado["p"]
        alt = dron.alt if dron.alt > 1 else 5

        print(f"Recalculo P con la posicion actual del dron: {posicion_dron}")
        print(f"Nuevo punto P: lat={lat}, lon={lon}, alt={alt}")
        dron.goto(lat, lon, alt)
        print("Ya he llegado al punto")

        # Si ya esta en el aire, fuerzo el estado para que Land entre sin problemas
        if dron.alt > 0.5:
            dron.state = "flying"

        if dron.Land():
            print("Aterrizando")
        else:
            print("No he podido hacer Land. El dron no estaba volando.")

    if dron is not None:
        try:
            dron.disconnect()
        except Exception:
            pass
