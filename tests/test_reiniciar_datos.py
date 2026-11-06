import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import reiniciar_datos
from core import reserva_express
from core.consumos import CONSUMOS_COLUMNS, agregar_consumo_detallado, obtener_resumen_habitacion


class TestReiniciarDatos(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.datos = Path(self.tmp.name)

        self.pasajeros = self.datos / 'pasajeros.csv'
        self.consumos = self.datos / 'consumos_diarios.csv'
        self.catalogo = self.datos / 'catalogo_productos.csv'

        pd.DataFrame([{
            'Nro. habitación': '101',
            'Fecha de ingreso': '01/01/2020',
            'Fecha de egreso': '02/01/2020',
            'Apellido y nombre': 'PASAJERO PRUEBA',
            'Voucher': 'V1',
            'id_estadia': 'ESTADIA-1',
        }]).to_csv(self.pasajeros, index=False)
        agregar_consumo_detallado(
            101, 'Bebidas', 1000, 'PASAJERO PRUEBA',
            archivo_consumos=str(self.consumos), id_estadia='ESTADIA-1',
        )
        self.catalogo.write_text(
            'codigo,producto,categoria,sector,precio_actual\nnampe_malbec,Nampe Malbec,vinos,Bar,6500\n',
            encoding='utf-8',
        )

    def test_simulacion_no_modifica_nada(self):
        antes = {p: p.read_bytes() for p in (self.pasajeros, self.consumos, self.catalogo)}

        plan, backup = reiniciar_datos.reiniciar(self.datos, simular=True)

        self.assertIsNone(backup)
        self.assertEqual(len(plan), 2)
        self.assertFalse((self.datos / 'backups').exists())
        for ruta, contenido in antes.items():
            self.assertEqual(ruta.read_bytes(), contenido)

    def test_reinicio_vacia_conserva_encabezados_y_respalda(self):
        original_pasajeros = self.pasajeros.read_bytes()
        original_consumos = self.consumos.read_bytes()
        catalogo = self.catalogo.read_bytes()

        _, backup = reiniciar_datos.reiniciar(
            self.datos, ahora=datetime(2026, 11, 7, 9, 30, 0)
        )

        self.assertEqual(backup.name, 'reinicio_20261107_093000')
        self.assertEqual((backup / 'pasajeros.csv').read_bytes(), original_pasajeros)
        self.assertEqual((backup / 'consumos_diarios.csv').read_bytes(), original_consumos)

        pasajeros = pd.read_csv(self.pasajeros)
        consumos = pd.read_csv(self.consumos)
        self.assertTrue(pasajeros.empty)
        self.assertIn('id_estadia', pasajeros.columns)
        self.assertTrue(consumos.empty)
        self.assertEqual(list(consumos.columns), CONSUMOS_COLUMNS)

        self.assertEqual(self.catalogo.read_bytes(), catalogo)

    def test_mantener_pasajeros_solo_vacia_consumos(self):
        original_pasajeros = self.pasajeros.read_bytes()

        _, backup = reiniciar_datos.reiniciar(self.datos, mantener_pasajeros=True)

        self.assertEqual(self.pasajeros.read_bytes(), original_pasajeros)
        self.assertTrue(pd.read_csv(self.consumos).empty)
        self.assertFalse((backup / 'pasajeros.csv').exists())

    def test_sin_archivos_previos_crea_consumos_vacio(self):
        self.pasajeros.unlink()
        self.consumos.unlink()

        _, backup = reiniciar_datos.reiniciar(self.datos)

        self.assertIsNone(backup)
        self.assertEqual(list(pd.read_csv(self.consumos).columns), CONSUMOS_COLUMNS)
        self.assertFalse(self.pasajeros.exists())

    def test_confirmacion_incorrecta_cancela(self):
        antes = self.consumos.read_bytes()
        with patch('builtins.input', return_value='no'):
            codigo = reiniciar_datos.main(['--datos', str(self.datos)])

        self.assertEqual(codigo, 1)
        self.assertEqual(self.consumos.read_bytes(), antes)
        self.assertFalse((self.datos / 'backups').exists())

    def test_sistema_funciona_desde_cero_tras_reiniciar(self):
        reiniciar_datos.reiniciar(self.datos)

        with patch.object(reserva_express, 'DB_PASAJEROS', str(self.pasajeros)):
            reserva, mensaje = reserva_express.crear_reserva_express(
                habitacion=101, nombre='PRIMER HUESPED REAL'
            )
        self.assertIsNotNone(reserva, mensaje)

        guardados = pd.read_csv(self.pasajeros, dtype={'id_estadia': str})
        self.assertEqual(len(guardados), 1)

        resumen = obtener_resumen_habitacion(
            101,
            {'id_estadia': reserva['id_estadia'], 'ids_estadia': [reserva['id_estadia']]},
            str(self.consumos),
        )
        self.assertEqual(resumen['cantidad_consumos'], 0)
        self.assertEqual(resumen['totales']['total'], 0)


if __name__ == '__main__':
    unittest.main()
