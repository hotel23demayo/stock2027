
import tempfile
import unittest
from pathlib import Path
from datetime import date

import pandas as pd

from core.dashboard import obtener_listado_pasajeros_alojados


class TestListadoPasajerosAlojados(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.csv_pasajeros = Path(self.tmp.name) / "pasajeros.csv"

        # Fecha fija para que las pruebas sean reproducibles.
        self.hoy = date(2026, 11, 1)

        filas = [
            {
                "Nro. habitación": "102",
                "Fecha de ingreso": "30/10/2026",
                "Fecha de egreso": "05/11/2026",
                "Apellido y nombre": "GOMEZ ANA",
                "Tipo documento": "DNI",
                "Nro. doc.": "11111111"
            },
            {
                "Nro. habitación": "102",
                "Fecha de ingreso": "30/10/2026",
                "Fecha de egreso": "05/11/2026",
                "Apellido y nombre": "GOMEZ LUIS",
                "Tipo documento": "DNI",
                "Nro. doc.": "22222222"
            },
            {
                "Nro. habitación": "101",
                "Fecha de ingreso": "01/11/2026",
                "Fecha de egreso": "03/11/2026",
                "Apellido y nombre": "PEREZ MARIA",
                "Tipo documento": "DNI",
                "Nro. doc.": "33333333"
            },
            {
                "Nro. habitación": "103",
                "Fecha de ingreso": "25/10/2026",
                "Fecha de egreso": "31/10/2026",
                "Apellido y nombre": "PASAJERO EGRESADO",
                "Tipo documento": "DNI",
                "Nro. doc.": "44444444"
            },
            {
                "Nro. habitación": "104",
                "Fecha de ingreso": "FECHA INVALIDA",
                "Fecha de egreso": "05/11/2026",
                "Apellido y nombre": "PASAJERO INVALIDO",
                "Tipo documento": "DNI",
                "Nro. doc.": "55555555"
            },
            {
                "Nro. habitación": "105",
                "Fecha de ingreso": "03/11/2026",
                "Fecha de egreso": "08/11/2026",
                "Apellido y nombre": "PASAJERO FUTURO",
                "Tipo documento": "DNI",
                "Nro. doc.": "66666666"
            }
        ]

        pd.DataFrame(filas).to_csv(
            self.csv_pasajeros,
            index=False
        )

    def obtener_listado(self):
        return obtener_listado_pasajeros_alojados(
            archivo_pasajeros=str(self.csv_pasajeros),
            fecha_referencia=self.hoy
        )

    def test_incluye_solo_pasajeros_alojados(self):
        resultado = self.obtener_listado()

        nombres = [
            pasajero["nombre"]
            for habitacion in resultado["habitaciones"]
            for pasajero in habitacion["pasajeros"]
        ]

        self.assertEqual(
            set(nombres),
            {"GOMEZ ANA", "GOMEZ LUIS", "PEREZ MARIA"}
        )

    def test_agrupa_pasajeros_por_habitacion(self):
        resultado = self.obtener_listado()

        habitaciones = resultado["habitaciones"]

        self.assertEqual(len(habitaciones), 2)

        self.assertEqual(habitaciones[0]["numero"], 101)
        self.assertEqual(habitaciones[0]["cantidad"], 1)

        self.assertEqual(habitaciones[1]["numero"], 102)
        self.assertEqual(habitaciones[1]["cantidad"], 2)

    def test_ordena_habitaciones_numericamente(self):
        resultado = self.obtener_listado()

        numeros = [
            habitacion["numero"]
            for habitacion in resultado["habitaciones"]
        ]

        self.assertEqual(numeros, [101, 102])

    def test_calcula_totales(self):
        resultado = self.obtener_listado()

        self.assertEqual(resultado["total_habitaciones"], 2)
        self.assertEqual(resultado["total_pasajeros"], 3)

    def test_incluye_fechas_limite(self):
        resultado = self.obtener_listado()

        nombres = [
            pasajero["nombre"]
            for habitacion in resultado["habitaciones"]
            for pasajero in habitacion["pasajeros"]
        ]

        # El ingreso es hoy: debe incluirse.
        self.assertIn("PEREZ MARIA", nombres)

    def test_documento_completo(self):
        resultado = self.obtener_listado()

        pasajero = resultado["habitaciones"][0]["pasajeros"][0]

        self.assertEqual(
            pasajero["documento"],
            "DNI 33333333"
        )

    def test_csv_inexistente_devuelve_resultado_vacio(self):
        resultado = obtener_listado_pasajeros_alojados(
            archivo_pasajeros=str(
                Path(self.tmp.name) / "inexistente.csv"
            ),
            fecha_referencia=self.hoy
        )

        self.assertEqual(resultado["total_habitaciones"], 0)
        self.assertEqual(resultado["total_pasajeros"], 0)
        self.assertEqual(resultado["habitaciones"], [])


if __name__ == "__main__":
    unittest.main()
