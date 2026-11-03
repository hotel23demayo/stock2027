import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core.consumos import (
    obtener_consumos_habitacion,
    obtener_resumen_habitacion,
    obtener_total_consumos,
)
from core.dashboard import (
    obtener_habitaciones_con_consumos,
    obtener_habitaciones_ocupadas,
    obtener_todos_pasajeros_habitacion,
)


class TestConsumosPorEstadia(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archivo = Path(self.tmp.name) / 'consumos.csv'

        pd.DataFrame([
            {
                'id_consumo': 'consumo-actual-1',
                'id_estadia': 'ESTADIA-A',
                'fecha': '03/11/2026 10:00',
                'habitacion': 105,
                'pasajero': 'HUÉSPED',
                'categoria': 'Bebidas',
                'monto': 1000,
                'estado': 'vigente',
            },
            {
                'id_consumo': 'consumo-actual-2',
                'id_estadia': 'ESTADIA-B',
                'fecha': '03/11/2026 10:05',
                'habitacion': 105,
                'pasajero': 'HUÉSPED',
                'categoria': 'Bebidas',
                'monto': 2000,
                'estado': 'vigente',
            },
            {
                'id_consumo': 'consumo-anterior',
                'id_estadia': 'ESTADIA-ANTERIOR',
                'fecha': '02/11/2026 10:00',
                'habitacion': 105,
                'pasajero': 'HUÉSPED',
                'categoria': 'Bebidas',
                'monto': 9000,
                'estado': 'vigente',
            },
            {
                'id_consumo': 'consumo-sin-estadia',
                'id_estadia': '',
                'fecha': '01/11/2026 10:00',
                'habitacion': 105,
                'pasajero': 'HUÉSPED',
                'categoria': 'Bebidas',
                'monto': 5000,
                'estado': 'vigente',
            },
        ]).to_csv(self.archivo, index=False)

    def test_consumos_y_totales_se_filtran_por_uno_o_varios_ids(self):
        consumos = obtener_consumos_habitacion(
            105,
            str(self.archivo),
            ['ESTADIA-A', 'ESTADIA-B'],
        )
        total = obtener_total_consumos(
            105,
            str(self.archivo),
            ['ESTADIA-A', 'ESTADIA-B'],
        )

        self.assertEqual(
            consumos['id_consumo'].tolist(),
            ['consumo-actual-1', 'consumo-actual-2'],
        )
        self.assertEqual(total['total'], 3000)

    def test_resumen_aisla_estadia_y_conserva_avisos_de_legacy(self):
        contenido_antes = self.archivo.read_bytes()

        with patch(
            'core.dashboard.obtener_todos_pasajeros_habitacion',
            return_value=[
                {'id_estadia': 'ESTADIA-A', 'nombre': 'HUÉSPED', 'voucher': 'A'},
                {'id_estadia': 'ESTADIA-B', 'nombre': 'HUÉSPED', 'voucher': 'B'},
            ],
        ):
            resumen = obtener_resumen_habitacion(
                105,
                {
                    'id_estadia': 'ESTADIA-A',
                    'ids_estadia': ['ESTADIA-A', 'ESTADIA-B'],
                    'pasajero': 'HUÉSPED',
                },
                str(self.archivo),
            )

        self.assertEqual(resumen['cantidad_consumos'], 2)
        self.assertEqual(resumen['totales']['total'], 3000)
        self.assertEqual(resumen['cantidad_consumos_sin_estadia'], 1)
        self.assertEqual(
            self.archivo.read_bytes(),
            contenido_antes,
        )

    def test_dashboard_solo_marca_consumos_de_estadias_activas(self):
        habitaciones = obtener_habitaciones_con_consumos(
            str(self.archivo),
            {
                105: {
                    'id_estadia': 'ESTADIA-A',
                    'ids_estadia': ['ESTADIA-A', 'ESTADIA-B'],
                },
                106: {
                    'id_estadia': 'ESTADIA-OTRA',
                    'ids_estadia': ['ESTADIA-OTRA'],
                },
            },
        )

        self.assertEqual(habitaciones, {105})

    def test_lista_de_pasajeros_excluye_estadias_ya_egresadas(self):
        archivo_pasajeros = Path(self.tmp.name) / 'pasajeros.csv'
        hoy = date.today()
        pd.DataFrame([
            {
                'Nro. habitación': 105,
                'Fecha de ingreso': (hoy - timedelta(days=4)).strftime('%d/%m/%Y'),
                'Fecha de egreso': (hoy - timedelta(days=1)).strftime('%d/%m/%Y'),
                'Apellido y nombre': 'HUÉSPED ANTERIOR',
                'Voucher': 'VOUCHER-ANTERIOR',
                'id_estadia': 'ESTADIA-ANTERIOR',
            },
            {
                'Nro. habitación': 105,
                'Fecha de ingreso': (hoy - timedelta(days=1)).strftime('%d/%m/%Y'),
                'Fecha de egreso': (hoy + timedelta(days=1)).strftime('%d/%m/%Y'),
                'Apellido y nombre': 'HUÉSPED ACTUAL',
                'Voucher': 'VOUCHER-ACTUAL',
                'id_estadia': 'ESTADIA-ACTUAL',
            },
        ]).to_csv(archivo_pasajeros, index=False)

        pasajeros = obtener_todos_pasajeros_habitacion(
            105,
            str(archivo_pasajeros),
        )

        self.assertEqual(
            [pasajero['id_estadia'] for pasajero in pasajeros],
            ['ESTADIA-ACTUAL'],
        )

    def test_ocupacion_actual_expone_ids_de_sus_pasajeros(self):
        archivo_pasajeros = Path(self.tmp.name) / 'pasajeros_actuales.csv'
        hoy = date.today()
        pd.DataFrame([
            {
                'Nro. habitación': 105,
                'Fecha de ingreso': (hoy - timedelta(days=4)).strftime('%d/%m/%Y'),
                'Fecha de egreso': (hoy - timedelta(days=1)).strftime('%d/%m/%Y'),
                'Apellido y nombre': 'HUÉSPED ANTERIOR',
                'Voucher': 'VOUCHER-ANTERIOR',
                'Edad': 50,
                'Servicios': '',
                'id_estadia': 'ESTADIA-ANTERIOR',
            },
            {
                'Nro. habitación': 105,
                'Fecha de ingreso': (hoy - timedelta(days=1)).strftime('%d/%m/%Y'),
                'Fecha de egreso': (hoy + timedelta(days=1)).strftime('%d/%m/%Y'),
                'Apellido y nombre': 'HUÉSPED ACTUAL',
                'Voucher': 'VOUCHER-ACTUAL',
                'Edad': 50,
                'Servicios': '',
                'id_estadia': 'ESTADIA-ACTUAL',
            },
        ]).to_csv(archivo_pasajeros, index=False)

        ocupadas = obtener_habitaciones_ocupadas(str(archivo_pasajeros))

        self.assertEqual(
            ocupadas[105]['ids_estadia'],
            ['ESTADIA-ACTUAL'],
        )


if __name__ == '__main__':
    unittest.main()
