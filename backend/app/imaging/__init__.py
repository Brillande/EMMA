"""Ecografía a bordo.

Por qué existe: en la ISS una ecografía se guía en directo desde control de misión, con
unos 2 s de retardo. Hacia Marte el retardo llega a unos 20 min por sentido y hay apagones:
nadie en Tierra puede mover la mano del operador. La tripulación tiene que poder adquirir,
medir y seguir la evolución sin Tierra, y eso es exactamente lo que EMMA ya hace con las
constantes. Este paquete extiende esa autonomía a la imagen.

Lo que NO hace: diagnosticar. Las medidas entran como observaciones del catálogo y pasan por
la misma línea base y el mismo motor de riesgo que el resto; la interpretación es apoyo a la
decisión (CLAUDE.md, invariante 7).
"""
