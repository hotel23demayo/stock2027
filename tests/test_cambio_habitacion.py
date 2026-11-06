import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import core.cambio_habitacion as cambio_habitacion


class TestCambioHabitacion(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.csv_pasajeros = str(
            Path(self.tmp.name) / "pasajeros.csv"
        )
        self.csv_consumos = str(
            Path(self.tmp.name) / "consumos_diarios.csv"
        )

        # Padrón sintético: dos pasajeros en la habitación física 101.
        # Los sufijos se conservan como referencias externas del contingente.
        pd.DataFrame([
            {
                "Nro. habitación": "101 A",
                "Apellido y nombre": "HUESPED A",
                "id_estadia": "ESTADIA-A",
                "Estado": "Activo",
            },
            {
                "Nro. habitación": "101 B",
                "Apellido y nombre": "HUESPED B",
                "id_estadia": "ESTADIA-B",
                "Estado": "Activo",
            },
        ]).to_csv(self.csv_pasajeros, index=False)

        # Consumos sintéticos de ambos pasajeros.
        pd.DataFrame([
            {
                "id_consumo": 1,
                "id_estadia": "ESTADIA-A",
                "habitacion": 101,
                "pasajero": "HUESPED A",
                "producto": "AGUA",
                "cantidad": 2,
                "estado": "Activo",
            },
            {
                "id_consumo": 2,
                "id_estadia": "ESTADIA-B",
                "habitacion": 101,
                "pasajero": "HUESPED B",
                "producto": "GASEOSA",
                "cantidad": 1,
                "estado": "Activo",
            },
            {
                "id_consumo": 3,
                "id_estadia": "ESTADIA-A-ANTERIOR",
                "habitacion": 101,
                "pasajero": "HUESPED A",
                "producto": "VINO HISTÓRICO",
                "cantidad": 1,
                "estado": "Activo",
            },
            {
                "id_consumo": 4,
                "habitacion": 101,
                "pasajero": "HUÉSPED LEGADO",
                "producto": "CONSUMO SIN ID",
                "cantidad": 1,
                "estado": "Activo",
            },
        ]).to_csv(self.csv_consumos, index=False)

        # Las funciones utilizarán exclusivamente los CSV temporales.
        self.patch_pasajeros = patch.object(
            cambio_habitacion,
            "DB_PASAJEROS",
            self.csv_pasajeros,
        )

        self.patch_consumos = patch.object(
            cambio_habitacion,
            "DB_CONSUMOS",
            self.csv_consumos,
        )

        self.patch_pasajeros.start()
        self.patch_consumos.start()

        self.addCleanup(self.patch_pasajeros.stop)
        self.addCleanup(self.patch_consumos.stop)

    def leer_pasajeros(self):
        return pd.read_csv(
            self.csv_pasajeros,
            dtype={
                "Nro. habitación": str,
                "id_estadia": str,
            },
        )

    def leer_consumos(self):
        return pd.read_csv(self.csv_consumos)

    def test_cambio_completo_traslada_pasajeros_y_consumos(self):

        exito, mensaje = cambio_habitacion.cambiar_habitacion(
            101,
            105,
            "Prueba de traslado",
        )

        self.assertTrue(exito, mensaje)

        pasajeros = self.leer_pasajeros()
        consumos = self.leer_consumos()

        # Ambos pasajeros deben pasar a la habitación física 105.
        self.assertEqual(
            pasajeros["Nro. habitación"].tolist(),
            ["105 A", "105 B"],
        )

        # Los identificadores de estadía deben conservarse.
        ids_estadia = dict(
            zip(
                pasajeros["Apellido y nombre"],
                pasajeros["id_estadia"],
            )
        )

        self.assertEqual(ids_estadia["HUESPED A"], "ESTADIA-A")
        self.assertEqual(ids_estadia["HUESPED B"], "ESTADIA-B")

        # Los dos consumos deben trasladarse a la habitación 105.
        self.assertEqual(
            consumos["habitacion"].tolist(),
            [105, 105, 101, 101],
        )

        # Deben conservarse identificadores y cantidades.
        self.assertEqual(
            consumos["id_consumo"].tolist(),
            [1, 2, 3, 4],
        )

        self.assertEqual(
            consumos["cantidad"].tolist(),
            [2, 1, 1, 1],
        )

        # También deben conservarse los estados.
        self.assertEqual(
            consumos["estado"].tolist(),
            ["Activo", "Activo", "Activo", "Activo"],
        )

    def test_no_permite_trasladar_a_habitacion_ocupada(self):

        pasajeros = self.leer_pasajeros()

        # Agregamos un tercer pasajero en la habitación 105.
        nuevo = pd.DataFrame([
            {
                "Nro. habitación": "105",
                "Apellido y nombre": "HUESPED C",
                "id_estadia": "ESTADIA-C",
                "Estado": "Activo",
            }
        ])

        pasajeros = pd.concat(
            [pasajeros, nuevo],
            ignore_index=True,
        )

        pasajeros.to_csv(self.csv_pasajeros, index=False)

        # Guardamos el estado previo.
        pasajeros_antes = self.leer_pasajeros().copy()
        consumos_antes = self.leer_consumos().copy()

        exito, mensaje = cambio_habitacion.cambiar_habitacion(
            101,
            105,
            "Prueba de destino ocupado",
        )

        self.assertFalse(exito, mensaje)

        pasajeros_despues = self.leer_pasajeros()
        consumos_despues = self.leer_consumos()

        # Ningún pasajero debe haberse movido.
        pd.testing.assert_frame_equal(
            pasajeros_antes,
            pasajeros_despues,
        )

        # Ningún consumo debe haberse modificado.
        pd.testing.assert_frame_equal(
            consumos_antes,
            consumos_despues,
        )
    def test_cambio_parcial_traslada_solo_un_pasajero_y_sus_consumos(self):

        exito, mensaje = cambio_habitacion.cambiar_pasajero_individual(
            101,
            105,
            "HUESPED A",
            "Prueba de traslado parcial",
        )

        self.assertTrue(exito, mensaje)

        pasajeros = self.leer_pasajeros()
        consumos = self.leer_consumos()

        # HUESPED A debe pasar a la habitación 105.
        huesped_a = pasajeros[
            pasajeros["Apellido y nombre"] == "HUESPED A"
        ]

        self.assertEqual(len(huesped_a), 1)

        habitacion_a = huesped_a.iloc[0]["Nro. habitación"]

        self.assertTrue(
            habitacion_a.startswith("105"),
            habitacion_a,
        )

        # HUESPED B debe permanecer en la habitación 101.
        huesped_b = pasajeros[
            pasajeros["Apellido y nombre"] == "HUESPED B"
        ]

        self.assertEqual(len(huesped_b), 1)
        self.assertEqual(
            huesped_b.iloc[0]["Nro. habitación"],
            "101 B",
        )

        # Los identificadores de estadía deben mantenerse.
        self.assertEqual(
            huesped_a.iloc[0]["id_estadia"],
            "ESTADIA-A",
        )

        self.assertEqual(
            huesped_b.iloc[0]["id_estadia"],
            "ESTADIA-B",
        )

        # Solamente los consumos de HUESPED A deben trasladarse.
        consumo_a = consumos[
            consumos["id_estadia"] == "ESTADIA-A"
        ]
        consumo_b = consumos[
            consumos["id_estadia"] == "ESTADIA-B"
        ]
        consumo_a_anterior = consumos[
            consumos["id_estadia"] == "ESTADIA-A-ANTERIOR"
        ]

        self.assertEqual(
            consumo_a.iloc[0]["habitacion"],
            105,
        )

        self.assertEqual(
            consumo_b.iloc[0]["habitacion"],
            101,
        )
        self.assertEqual(
            consumo_a_anterior.iloc[0]["habitacion"],
            101,
        )
        self.assertEqual(
            consumos.loc[
                consumos["id_consumo"] == 4,
                "habitacion",
            ].iloc[0],
            101,
        )

        # Los identificadores y cantidades deben conservarse.
        self.assertEqual(
            consumos["id_consumo"].tolist(),
            [1, 2, 3, 4],
        )

        self.assertEqual(
            consumos["cantidad"].tolist(),
            [2, 1, 1, 1],
        )
    def test_cambio_parcial_a_habitacion_ocupada_con_cupo(self):

        pasajeros = self.leer_pasajeros()

        # HUESPED C ya se encuentra alojado en la habitación 105.
        nuevo = pd.DataFrame([
            {
                "Nro. habitación": "105",
                "Apellido y nombre": "HUESPED C",
                "id_estadia": "ESTADIA-C",
                "Estado": "Activo",
            }
        ])

        pasajeros = pd.concat(
            [pasajeros, nuevo],
            ignore_index=True,
        )

        pasajeros.to_csv(self.csv_pasajeros, index=False)

        # Registramos el estado previo de HUESPED C.
        pasajero_c_antes = self.leer_pasajeros()
        pasajero_c_antes = pasajero_c_antes[
            pasajero_c_antes["Apellido y nombre"] == "HUESPED C"
        ].copy()

        consumos_antes = self.leer_consumos().copy()

        exito, mensaje = cambio_habitacion.cambiar_pasajero_individual(
            101,
            105,
            "HUESPED A",
            "Prueba de destino ocupado con cupo",
        )

        self.assertTrue(exito, mensaje)

        pasajeros_despues = self.leer_pasajeros()
        consumos_despues = self.leer_consumos()

        # A debe pasar a 105.
        huesped_a = pasajeros_despues[
            pasajeros_despues["Apellido y nombre"] == "HUESPED A"
        ]

        self.assertEqual(len(huesped_a), 1)
        self.assertTrue(
            huesped_a.iloc[0]["Nro. habitación"].startswith("105")
        )

        # B debe permanecer en 101.
        huesped_b = pasajeros_despues[
            pasajeros_despues["Apellido y nombre"] == "HUESPED B"
        ]

        self.assertEqual(
            huesped_b.iloc[0]["Nro. habitación"],
            "101 B",
        )

        # C debe conservar su habitación y estadía.
        pasajero_c_despues = pasajeros_despues[
            pasajeros_despues["Apellido y nombre"] == "HUESPED C"
        ]

        pd.testing.assert_frame_equal(
            pasajero_c_antes.reset_index(drop=True),
            pasajero_c_despues.reset_index(drop=True),
        )

        # Los consumos anteriores de C deben permanecer intactos.
        pd.testing.assert_frame_equal(
            consumos_antes[
                consumos_antes["pasajero"] == "HUESPED C"
            ].reset_index(drop=True),
            consumos_despues[
                consumos_despues["pasajero"] == "HUESPED C"
            ].reset_index(drop=True),
        )

        # Los consumos de A deben quedar en 105.
        consumo_a = consumos_despues[
            consumos_despues["pasajero"] == "HUESPED A"
        ]

        self.assertEqual(
            consumo_a.iloc[0]["habitacion"],
            105,
        )
        self.assertEqual(
            consumo_a.iloc[1]["habitacion"],
            101,
        )
        self.assertEqual(
            consumos_despues.loc[
                consumos_despues["id_consumo"] == 4,
                "habitacion",
            ].iloc[0],
            101,
        )
if __name__ == "__main__":
    unittest.main()