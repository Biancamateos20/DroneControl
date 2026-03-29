import argparse
import math


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


def _latlon_a_local(origen, punto):
    lat0, lon0 = map(math.radians, origen)
    lat, lon = map(math.radians, punto)

    x = (lon - lon0) * RADIO_TIERRA_M * math.cos(lat0)
    y = (lat - lat0) * RADIO_TIERRA_M
    return x, y


def _local_a_latlon(origen, punto):
    lat0, lon0 = origen
    x, y = punto

    lat = lat0 + math.degrees(y / RADIO_TIERRA_M)
    lon = lon0 + math.degrees(x / (RADIO_TIERRA_M * math.cos(math.radians(lat0))))
    return lat, lon


def _resta(a, b):
    return a[0] - b[0], a[1] - b[1]


def _suma(a, b):
    return a[0] + b[0], a[1] + b[1]


def _escala(v, escalar):
    return v[0] * escalar, v[1] * escalar


def _producto_cruz(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _distancia(a, b):
    return math.dist(a, b)


def _punto_en_poligono(punto, poligono):
    x, y = punto
    dentro = False

    for i in range(len(poligono)):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % len(poligono)]

        cruza = (y1 > y) != (y2 > y)
        if cruza:
            x_interseccion = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_interseccion:
                dentro = not dentro

    return dentro


def _interseccion_segmentos(origen, destino, inicio, fin, epsilon=1e-9):
    direccion = _resta(destino, origen)
    lado = _resta(fin, inicio)
    denominador = _producto_cruz(direccion, lado)

    if abs(denominador) < epsilon:
        return None

    delta = _resta(inicio, origen)
    t = _producto_cruz(delta, lado) / denominador
    u = _producto_cruz(delta, direccion) / denominador

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        punto = _suma(origen, _escala(direccion, t))
        return t, punto

    return None


def _intersecciones_segmento_poligono(origen, destino, poligono, tipo_fence):
    intersecciones = []

    for i in range(len(poligono)):
        inicio = poligono[i]
        fin = poligono[(i + 1) % len(poligono)]
        interseccion = _interseccion_segmentos(origen, destino, inicio, fin)
        if interseccion is None:
            continue

        t, punto = interseccion
        intersecciones.append(
            {
                "tipo": tipo_fence,
                "t": t,
                "punto_local": punto,
                "segmento": (inicio, fin),
            }
        )

    return intersecciones


def _normalizar(v):
    longitud = math.hypot(v[0], v[1])
    if longitud == 0:
        raise ValueError("El dron y el usuario estan en el mismo punto.")
    return v[0] / longitud, v[1] / longitud


def _primer_fence_en_trayectoria(escenario, dron, destino):
    dron_local = (0.0, 0.0)
    destino_local = _latlon_a_local(dron, destino)
    inclusion = escenario[0]

    if inclusion["type"] != "polygon":
        raise ValueError("El primer fence del scenario debe ser un poligono de inclusion.")

    inclusion_local = [
        _latlon_a_local(dron, (wp["lat"], wp["lon"]))
        for wp in inclusion["waypoints"]
    ]

    if not _punto_en_poligono(dron_local, inclusion_local):
        raise ValueError("El dron D debe estar dentro del fence de inclusion.")

    candidatos = _intersecciones_segmento_poligono(
        dron_local,
        destino_local,
        inclusion_local,
        "inclusion_polygon",
    )

    epsilon = 1e-6
    candidatos_validos = [c for c in candidatos if c["t"] > epsilon]
    if not candidatos_validos:
        raise ValueError("La trayectoria D -> M no corta el poligono del geofence.")

    return min(candidatos_validos, key=lambda candidato: candidato["t"]), destino_local


def calculo(escenario, dron, usuario, margen_metros):
    if margen_metros < 0:
        raise ValueError("La distancia de margen no puede ser negativa.")

    interseccion, destino_local = _primer_fence_en_trayectoria(escenario, dron, usuario)
    punto_fence = interseccion["punto_local"]
    distancia_al_fence = _distancia((0.0, 0.0), punto_fence)

    if margen_metros >= distancia_al_fence:
        raise ValueError(
            f"El fence se alcanza a {distancia_al_fence:.2f} m; "
            f"no se puede frenar {margen_metros:.2f} m antes."
        )

    direccion = _normalizar(_resta(destino_local, (0.0, 0.0)))
    punto_parada_local = _suma(
        punto_fence,
        _escala(direccion, -margen_metros),
    )

    resultado = {
        "usuario": usuario,
        "p": _local_a_latlon(dron, punto_parada_local),
        "fence_mas_cercano": interseccion["tipo"],
        "distancia_desde_dron_al_fence_m": distancia_al_fence,
        "distancia_desde_p_al_fence_m": _distancia(punto_parada_local, punto_fence),
        "margen_solicitado_m": margen_metros,
        "punto_fence": _local_a_latlon(dron, punto_fence),
    }

    if "segmento" in interseccion:
        resultado["segmento_fence"] = (
            _local_a_latlon(dron, interseccion["segmento"][0]),
            _local_a_latlon(dron, interseccion["segmento"][1]),
        )

    return resultado


def caculo(escenario, D, M, d):
    return calculo(escenario, D, M, d)


def _leer_argumentos():
    parser = argparse.ArgumentParser(
        description="Calcula el punto P donde debe pararse el dron antes de tocar el geofence."
    )
    parser.add_argument(
        "usuario",
        nargs="?",
        choices=sorted(USUARIOS.keys()),
        help="Usuario destino: m1, m2 o m3.",
    )
    parser.add_argument(
        "margen",
        nargs="?",
        type=float,
        help="Metros antes del geofence donde debe detenerse el dron.",
    )
    return parser.parse_args()


def _leer_usuario_terminal():
    usuario = input("Elige usuario destino (m1, m2 o m3): ").strip().lower()
    if usuario not in USUARIOS:
        raise ValueError("Usuario no valido. Debe ser m1, m2 o m3.")
    return usuario


def _leer_margen_terminal():
    return float(input("Introduce los metros antes del geofence para parar el dron: ").replace(",", "."))


def main():
    args = _leer_argumentos()
    usuario_id = args.usuario or _leer_usuario_terminal()
    margen = args.margen if args.margen is not None else _leer_margen_terminal()
    usuario = USUARIOS[usuario_id]

    resultado = calculo(SCENARIO, D, usuario, margen)
    punto_p = resultado["p"]
    punto_fence = resultado["punto_fence"]

    print("Scenario usado como geofence del dron")
    print(f"Dron D: lat={D[0]:.7f}, lon={D[1]:.7f}")
    print(f"Usuario {usuario_id.upper()}: lat={usuario[0]:.7f}, lon={usuario[1]:.7f}")
    print(f"Primer fence en la trayectoria: {resultado['fence_mas_cercano']}")
    print(f"Punto donde la trayectoria toca el fence: lat={punto_fence[0]:.7f}, lon={punto_fence[1]:.7f}")
    print(f"Distancia desde D hasta ese fence: {resultado['distancia_desde_dron_al_fence_m']:.2f} m")
    print(f"Distancia exacta desde P hasta el fence: {resultado['distancia_desde_p_al_fence_m']:.6f} m")
    print(f"Punto P de parada a {margen:.2f} m antes del geofence: lat={punto_p[0]:.7f}, lon={punto_p[1]:.7f}")


if __name__ == "__main__":
    main()
