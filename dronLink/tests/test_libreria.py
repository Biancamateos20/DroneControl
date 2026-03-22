import time
from DronLink.dronLink.Dron import Dron

dron = Dron ()
connection_string = 'tcp:127.0.0.1:5762'
baud = 115200
connection_string = 'com3'
baud = 57600
dron.connect(connection_string, baud)
print ('conectado')
dron.arm()
print ('ya he armado')
dron.takeOff (3)
print ('ya he alcanzado al altitud indicada. Espero 5 segundos')
#time.sleep (5)
#dron.fixHeading()
print ('vamos hacia delante durante 5 segundos')
dron.go('Forward')
time.sleep (3)
dron.go('Left')
time.sleep (3)
dron.changeNavSpeed(0.5)
dron.go('Forward')
time.sleep (3)
'''print ('voy a rotar 90')
dron.rotate(90)
print ('ya he girado. Ahora espero 15 segundos')
time.sleep (15)
print ('vamos hacia delante durante 5 segundos')
dron.go('Forward')
time.sleep (5)
print ('vamos a rotar 180')
dron.rotate(180)
print ('vamos a aterrizar')'''
dron.Land()
print ('ya estoy en tierra')
dron.disconnect()