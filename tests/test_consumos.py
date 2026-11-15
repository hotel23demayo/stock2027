import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.consumos import (
    agregar_consumo_bebida_rapida,
    obtener_catalogo_bebidas,
    obtener_consumos_habitacion,
    obtener_total_consumos,
)


class TestConsumos(unittest.TestCase):

    def test_iconos_de_cafe_y_aguas_saborizadas(self):
        catalogo = {producto['codigo']: producto for producto in obtener_catalogo_bebidas()}
        self.assertEqual(catalogo['ficha_cafe']['icono'], '☕')
        self.assertEqual(catalogo['saborizada_manzana']['icono'], '🧃')
        self.assertEqual(catalogo['saborizada_pomelo']['icono'], '🧃')

    def test_agregar_bebida_con_cantidad_y_precio_correctos(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = str(Path(tmp) / "consumos_prueba.csv")

            exito, mensaje = agregar_consumo_bebida_rapida(
                num_habitacion=999,
                producto_codigo="nampe_malbec",
                cantidad=2,
                pasajero="PASAJERO DE PRUEBA",
                archivo_consumos=archivo,
            )

            self.assertTrue(exito, mensaje)

            consumos = obtener_consumos_habitacion(999, archivo)

            self.assertEqual(len(consumos), 1)
            self.assertEqual(consumos.iloc[0]["item"], "Nampe Malbec")
            self.assertEqual(int(consumos.iloc[0]["cantidad"]), 2)
            self.assertEqual(float(consumos.iloc[0]["precio_unitario"]), 6500.0)
            self.assertEqual(float(consumos.iloc[0]["monto"]), 13000.0)

            totales = obtener_total_consumos(999, archivo)
            self.assertEqual(float(totales["total"]), 13000.0)

    def test_cantidad_cero_no_debe_generar_consumo(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = str(Path(tmp) / "consumos_prueba.csv")

            exito, mensaje = agregar_consumo_bebida_rapida(
                num_habitacion=999,
                producto_codigo="nampe_malbec",
                cantidad=0,
                pasajero="PASAJERO DE PRUEBA",
                archivo_consumos=archivo,
            )

            self.assertFalse(exito)
            self.assertIn("mayor a cero", mensaje)
            self.assertFalse(Path(archivo).exists())

    def test_producto_inexistente_no_debe_generar_consumo(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = str(Path(tmp) / "consumos_prueba.csv")

            exito, mensaje = agregar_consumo_bebida_rapida(
                num_habitacion=999,
                producto_codigo="producto_inexistente",
                cantidad=1,
                pasajero="PASAJERO DE PRUEBA",
                archivo_consumos=archivo,
            )

            self.assertFalse(exito)
            self.assertIn("no válido", mensaje)
            self.assertFalse(Path(archivo).exists())


if __name__ == "__main__":
    unittest.main()
