import math

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
    ("tcp:127.0.0.1:5763", 115200),
    ("tcp:127.0.0.1:5762", 115200),
    ("udp:127.0.0.1:14551", 115200),
]


def a_local(origen, punto):
    lat0, lon0 = map(math.radians, origen)
    lat, lon = map(math.radians, punto)
    x = (lon - lon0) * RADIO_TIERRA_M * math.cos(lat0)
    y = (lat - lat0) * RADIO_TIERRA_M
    return x, y


def a_global(origen, punto):
    lat0, lon0 = origen
    x, y = punto
    lat = lat0 + math.degrees(y / RADIO_TIERRA_M)
    lon = lon0 + math.degrees(x / (RADIO_TIERRA_M * math.cos(math.radians(lat0))))
    return lat, lon


def distancia(a, b):
    return math.dist(a, b)


def leer_escenario():
    if Dron is None:
        return SCENARIO, "scenario hardcodeado"

    for conexion, baud in CONEXIONES:
        dron = Dron()
        try:
            dron.connect(conexion, baud)
            escenario = dron.getScenario()
            if escenario:
                return escenario, f"geofence del dron ({conexion})"
        except Exception:
            pass
        finally:
            try:
                dron.disconnect()
            except Exception:
                pass

    return SCENARIO, "scenario hardcodeado"


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
            den = dx * sy - dy * sx

            if abs(den) < 1e-9:
                continue

            qx = a[0] - origen[0]
            qy = a[1] - origen[1]
            t = (qx * sy - qy * sx) / den
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

    if margen >= distancia_fence:
        raise ValueError(
            f"El fence se alcanza a {distancia_fence:.2f} m; "
            f"no se puede frenar {margen:.2f} m antes."
        )

    largo = math.hypot(destino[0], destino[1])
    if largo == 0:
        raise ValueError("El dron y el usuario estan en el mismo punto.")

    punto_parada = (
        punto_fence[0] - destino[0] * margen / largo,
        punto_fence[1] - destino[1] * margen / largo,
    )

    resultado = {
        "usuario": M,
        "p": a_global(D, punto_parada),
        "fence_mas_cercano": corte["tipo"],
        "distancia_desde_dron_al_fence_m": distancia_fence,
        "distancia_desde_p_al_fence_m": distancia(punto_parada, punto_fence),
        "margen_solicitado_m": margen,
        "punto_fence": a_global(D, punto_fence),
    }

    if "segmento" in corte:
        a, b = corte["segmento"]
        resultado["segmento_fence"] = (a_global(D, a), a_global(D, b))

    return resultado


if __name__ == "__main__":
    escenario, origen = leer_escenario()
    resultado = calculo(escenario, D, USUARIOS["m1"], 3)
    print(origen)
    print(resultado)
