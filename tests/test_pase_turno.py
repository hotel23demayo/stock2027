import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app as aplicacion
from core.pase_caja import consolidar_salidas_por_habitacion


class TestPaseTurno(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directorio = Path(self.tmp.name)
        self.csv_pasajeros = directorio / 'pasajeros.csv'
        self.csv_consumos = directorio / 'consumos.csv'

        pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104',
            'Apellido y nombre': 'JUAN GOMEZ',
            'Fecha de ingreso': date.today().strftime('%d/%m/%Y'),
            'Fecha de egreso': date.today().strftime('%d/%m/%Y'),
            'Voucher': 'V-001'
        }]).to_csv(self.csv_pasajeros, index=False)

        self.df_consumos = pd.DataFrame(columns=[
            'id_consumo', 'id_estadia', 'fecha', 'habitacion', 'pasajero',
            'categoria', 'item', 'cantidad', 'precio_unitario', 'monto',
            'estado', 'fecha_anulacion', 'motivo_anulacion'
        ])
        self.df_consumos.to_csv(self.csv_consumos, index=False)

        self.patcher_pasajeros = patch.object(
            aplicacion,
            'DB_PASAJEROS',
            str(self.csv_pasajeros)
        )
        self.patcher_consumos = patch.object(
            aplicacion,
            'DB_CONSUMOS',
            str(self.csv_consumos)
        )
        self.patcher_pasajeros.start()
        self.patcher_consumos.start()
        self.addCleanup(self.patcher_pasajeros.stop)
        self.addCleanup(self.patcher_consumos.stop)
        self.cliente = aplicacion.app.test_client()

    def test_muestra_sin_deuda_confirmada(self):
        respuesta = self.cliente.get('/pase-turno')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b'Sin deuda de bebidas', respuesta.data)
        self.assertIn(b'No se registran bebidas confirmadas a cobrar', respuesta.data)
        self.assertIn(b'$ 0', respuesta.data)
        html = respuesta.data.decode('utf-8')
        planilla = html.split(
            '<section class="impresion-planilla"',
            1
        )[1].split('</section>', 1)[0]
        self.assertIn('Turno: 00 a 08 hs', planilla)
        self.assertIn(f'Fecha: {date.today().strftime("%d/%m/%Y")}', planilla)
        self.assertNotIn('Emisión:', planilla)
        self.assertNotIn('Sin deuda de bebidas', planilla)
        self.assertNotIn('TOTAL BEBIDAS A COBRAR', planilla)
        self.assertEqual(planilla.count('<tr>'), 29)

    def test_muestra_importe_confirmado_a_cobrar(self):
        self.df_consumos = pd.DataFrame([{
            'id_consumo': 'CON-001',
            'id_estadia': 'EST-001',
            'fecha': date.today().strftime('%d/%m/%Y'),
            'habitacion': '104',
            'pasajero': 'JUAN GOMEZ',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'cantidad': '1',
            'precio_unitario': '1500',
            'monto': '1500',
            'estado': 'vigente',
            'fecha_anulacion': '',
            'motivo_anulacion': ''
        }])
        self.df_consumos.to_csv(self.csv_consumos, index=False)

        respuesta = self.cliente.get('/pase-turno')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b'A cobrar', respuesta.data)
        self.assertIn(b'Total confirmado de bebidas a cobrar', respuesta.data)
        self.assertIn(b'$ 1.500', respuesta.data)
        self.assertIn(b'Agua', respuesta.data)

    def test_consolidar_salidas_por_habitacion_y_voucher(self):
        salidas = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '117',
                'Apellido y nombre': 'GOMEZ JUAN',
                'Voucher': 'V001'
            },
            {
                'id_estadia': 'EST-002',
                'Nro. habitación': '117',
                'Apellido y nombre': 'PEREZ MARIA',
                'Voucher': 'V002'
            },
            {
                'id_estadia': 'EST-003',
                'Nro. habitación': '118',
                'Apellido y nombre': 'DE LA TORRE ANA',
                'Voucher': 'V003'
            },
            {
                'id_estadia': 'EST-004',
                'Nro. habitación': '118',
                'Apellido y nombre': 'TORRES CARLOS',
                'Voucher': 'V003'
            },
            {
                'id_estadia': 'EST-005',
                'Nro. habitación': '119',
                'Apellido y nombre': 'LOPEZ MARTA',
                'Voucher': 'V001'
            }
        ])

        totales = {
            'EST-001': 1500.0,
            'EST-002': 2500.0,
            'EST-003': 1000.0,
            'EST-004': 2000.0,
            'EST-005': 500.0
        }

        filas = consolidar_salidas_por_habitacion(
            salidas,
            totales
        )

        self.assertEqual(len(filas), 4)

        # Habitación 117: dos vouchers independientes.
        self.assertEqual(filas.iloc[0]['habitacion'], '117')
        self.assertEqual(filas.iloc[0]['titular'], 'GOMEZ JUAN')
        self.assertEqual(filas.iloc[0]['bebidas'], 1500.0)

        self.assertEqual(filas.iloc[1]['habitacion'], '117')
        self.assertEqual(filas.iloc[1]['titular'], 'PEREZ MARIA')
        self.assertEqual(filas.iloc[1]['bebidas'], 2500.0)

        # Habitación 118: dos pasajeros comparten voucher.
        self.assertEqual(filas.iloc[2]['habitacion'], '118')
        self.assertEqual(filas.iloc[2]['titular'], 'DE LA TORRE ANA')
        self.assertEqual(filas.iloc[2]['bebidas'], 3000.0)

        # El mismo voucher en otra habitación es otra cuenta.
        self.assertEqual(filas.iloc[3]['habitacion'], '119')
        self.assertEqual(filas.iloc[3]['titular'], 'LOPEZ MARTA')
        self.assertEqual(filas.iloc[3]['bebidas'], 500.0)