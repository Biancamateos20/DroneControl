import argparse
import math


RADIO_TIERRA_M = 6371000.0

M1 = (41.276380, 1.988146)
M2 = (41.276568, 1.988428)
M3 = (41.276304, 1.989122)
D = (41.276443, 1.988586)

SCENARIO = [
    {
        "type": "polygon",
        "waypoints": [
            {"lat": M1[0], "lon": M1[1]},
            {"lat": M2[0], "lon": M2[1]},
            {"lat": M3[0], "lon": M3[1]},
        ],
    }
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


def _proyeccion_punto_a_segmento(punto, inicio, fin):
    px, py = punto
    x1, y1 = inicio
    x2, y2 = fin

    dx = x2 - x1
    dy = y2 - y1
    longitud2 = dx * dx + dy * dy

    if longitud2 == 0:
        return inicio, math.dist(punto, inicio)

    t = ((px - x1) * dx + (py - y1) * dy) / longitud2
    t = max(0.0, min(1.0, t))

    proyeccion = (x1 + t * dx, y1 + t * dy)
    return proyeccion, math.dist(punto, proyeccion)


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


def _punto_mas_cercano_al_geofence(dron_local, poligono_local):
    mejor_punto = None
    mejor_distancia = float("inf")
    mejor_segmento = None

    for i in range(len(poligono_local)):
        inicio = poligono_local[i]
        fin = poligono_local[(i + 1) % len(poligono_local)]
        proyeccion, distancia = _proyeccion_punto_a_segmento(dron_local, inicio, fin)

        if distancia < mejor_distancia:
            mejor_punto = proyeccion
            mejor_distancia = distancia
            mejor_segmento = (inicio, fin)

    return mejor_punto, mejor_distancia, mejor_segmento


def calculo(escenario, dron, margen_metros):
    if margen_metros < 0:
        raise ValueError("La distancia de margen no puede ser negativa.")

    inclusion = escenario[0]
    if inclusion["type"] != "polygon":
        raise ValueError("Este calculo solo esta implementado para geofence poligonal.")

    poligono_geo = [(wp["lat"], wp["lon"]) for wp in inclusion["waypoints"]]
    poligono_local = [_latlon_a_local(dron, punto) for punto in poligono_geo]
    dron_local = (0.0, 0.0)

    if not _punto_en_poligono(dron_local, poligono_local):
        raise ValueError("El punto del dron no esta dentro del geofence.")

    borde_local, distancia_borde, segmento = _punto_mas_cercano_al_geofence(dron_local, poligono_local)

    if margen_metros >= distancia_borde:
        raise ValueError(
            f"El dron ya esta a {distancia_borde:.2f} m del geofence; "
            f"no se puede dejar un margen de {margen_metros:.2f} m."
        )

    factor = margen_metros / distancia_borde
    punto_parada_local = (
        borde_local[0] * (1.0 - factor),
        borde_local[1] * (1.0 - factor),
    )

    punto_parada_geo = _local_a_latlon(dron, punto_parada_local)
    punto_borde_geo = _local_a_latlon(dron, borde_local)

    return {
        "p": punto_parada_geo,
        "distancia_actual_al_geofence_m": distancia_borde,
        "margen_solicitado_m": margen_metros,
        "punto_borde_mas_cercano": punto_borde_geo,
        "segmento_mas_cercano": (
            _local_a_latlon(dron, segmento[0]),
            _local_a_latlon(dron, segmento[1]),
        ),
    }


def caculo(escenario, D, M, d):
    return calculo(escenario, D, d)


def _leer_argumentos():
    parser = argparse.ArgumentParser(
        description="Calcula el punto P donde debe pararse el dron antes de llegar al geofence."
    )
    parser.add_argument(
        "margen",
        nargs="?",
        type=float,
        help="Metros antes del geofence donde debe detenerse el dron.",
    )
    return parser.parse_args()


def main():
    args = _leer_argumentos()
    margen = args.margen

    if margen is None:
        margen = float(input("Introduce los metros antes del geofence para parar el dron: ").replace(",", "."))

    resultado = calculo(SCENARIO, D, margen)
    punto_p = resultado["p"]
    punto_borde = resultado["punto_borde_mas_cercano"]

    print("Geofence definido por M1, M2 y M3")
    print(f"Dron D: lat={D[0]:.7f}, lon={D[1]:.7f}")
    print(f"Distancia actual al geofence: {resultado['distancia_actual_al_geofence_m']:.2f} m")
    print(f"Punto del borde mas cercano: lat={punto_borde[0]:.7f}, lon={punto_borde[1]:.7f}")
    print(f"Punto P de parada a {margen:.2f} m del geofence: lat={punto_p[0]:.7f}, lon={punto_p[1]:.7f}")


if __name__ == "__main__":
    main()
