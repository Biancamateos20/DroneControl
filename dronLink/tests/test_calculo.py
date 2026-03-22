
import json

from DronLink.dronLink.Dron import Dron
def caculo (escenario,D,M,d):

     P = None
     return P

dron = Dron ()
connection_string = 'com3'
baud = 57600
dron.connect(connection_string, baud)
scenario = dron.getScenario()
print ('Este es el escenario que hay en este momento en el autopiloto')
print (json.dumps(scenario, indent = 1))
D = (41.276443, 1.988586)
M1 = (41.276380, 1.988146)
M2 = (41.276568, 1.988428)
M3 = (41.276304, 1.989122)
