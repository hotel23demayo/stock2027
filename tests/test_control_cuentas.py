import tempfile
import unittest
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app as aplicacion
from core.control_cuentas import generar_control_cuentas
from core.pase_caja import COLUMNAS_CONSUMOS, COLUMNAS_PASAJEROS


class LectorEnlacesDashboard(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paneles = []
        self.enlaces = []
        self.enlace_actual = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section':
            self.paneles.append(attrs.get('id'))
        if tag == 'a' and attrs.get('href') == '/control-cuentas':
            self.enlace_actual = {'paneles': tuple(self.paneles), 'texto': ''}
            self.enlaces.append(self.enlace_actual)

    def handle_data(self, data):
        if self.enlace_actual is not None:
            self.enlace_actual['texto'] += data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.enlace_actual = None
        elif tag == 'section' and self.paneles:
            self.paneles.pop()


def pasajero(identificador, habitacion, voucher, ingreso='01/11/2026', egreso='05/11/2026'):
    return {
        'id_estadia': identificador, 'Nro. habitación': habitacion,
        'Apellido y nombre': identificador, 'Voucher': voucher,
        'Fecha de ingreso': ingreso, 'Fecha de egreso': egreso,
    }


def consumo(identificador, habitacion='101', monto='100', estado='vigente',
            cantidad='2', categoria='Bebidas', item='Agua'):
    return {
        'id_consumo': 'C-' + identificador, 'id_estadia': identificador,
        'habitacion': habitacion, 'monto': monto, 'estado': estado,
        'cantidad': cantidad, 'categoria': categoria, 'item': item,
        'fecha': '02/11/2026 10:00', 'pasajero': identificador,
        'precio_unitario': '50', 'fecha_anulacion': '', 'motivo_anulacion': '',
    }


class TestControlCuentas(unittest.TestCase):
    def generar(self, pasajeros, consumos):
        return generar_control_cuentas(
            pd.DataFrame(pasajeros, columns=COLUMNAS_PASAJEROS),
            pd.DataFrame(consumos, columns=COLUMNAS_CONSUMOS),
            date(2026, 11, 2),
        )

    def test_agrupacion_fechas_consumos_y_anulaciones(self):
        pasajeros = [
            pasajero('A', '101', 'V1', ingreso='02/11/2026'),
            pasajero('B', '101', 'V1', egreso='02/11/2026'),
            pasajero('C', '101', 'V2'),
            pasajero('D', '102', 'V1'),
            pasajero('E', '103', 'V3'),
            pasajero('SALIDA', '104', 'V4', egreso='01/11/2026'),
            pasajero('FUTURO', '105', 'V5', ingreso='03/11/2026'),
        ]
        consumos = [
            consumo('A'), consumo('A', monto='50', cantidad='1'),
            consumo('B', monto='200', cantidad='4'),
            consumo('B', monto='999', estado='anulado', item='Anulado'),
            consumo('B', monto='999', categoria='Comida'),
            consumo('C', monto='300'), consumo('D', habitacion='102', monto='400'),
            consumo('SALIDA', habitacion='104', monto='999'),
        ]
        resultado = self.generar(pasajeros, consumos)
        cuentas = resultado['cuentas']
        self.assertEqual([(c['habitacion'], c['voucher']) for c in cuentas],
                         [('101', 'V1'), ('101', 'V2'), ('102', 'V1'), ('103', 'V3')])
        self.assertEqual([c['bebidas'] for c in cuentas], [350, 300, 400, 0])
        self.assertEqual(cuentas[0]['titular'], 'A')
        self.assertEqual(cuentas[0]['pasajeros'], ['A', 'B'])
        self.assertEqual(cuentas[0]['unidades'], 7)
        self.assertEqual(len(cuentas[0]['detalle']), 4)
        self.assertIn('anulado', [c['estado'] for c in cuentas[0]['detalle']])
        self.assertEqual(resultado['total_bebidas'], 1050)
        self.assertEqual(resultado['total_pasajeros'], 5)
        self.assertEqual(resultado['total_habitaciones'], 3)
        self.assertEqual(resultado['cuentas_con_consumos'], 3)

    def test_observa_identidades_habitaciones_importes_y_estados(self):
        pasajeros = [
            pasajero('A', '101', 'V1'),
            pasajero('DUP', '101', 'V1'),
            pasajero('DUP', '102', 'V2'),
            pasajero('INACTIVO', '101', 'V3', egreso='01/11/2026'),
        ]
        consumos = [
            consumo('', monto='500'),
            consumo('DUP', monto='500'),
            consumo('A', habitacion='102', monto='500'),
            consumo('A', monto='no-numero'),
            consumo('A', monto='-1'),
            consumo('A', monto='nan'),
            consumo('A', estado='desconocido'),
            consumo('INACTIVO'),
            consumo('A', habitacion='102', estado='anulado'),
            consumo('A', monto='0', cantidad=''),
        ]
        resultado = self.generar(pasajeros, consumos)
        self.assertEqual(resultado['total_bebidas'], 0)
        motivos = [obs['motivo'] for obs in resultado['observaciones']]
        self.assertIn('Consumo sin id_estadia', motivos)
        self.assertIn('id_estadia duplicado en el padrón; consumos excluidos', motivos)
        self.assertIn('Consumo con id_estadia duplicado', motivos)
        self.assertIn('Consumo de una estadía no activa en habitación ocupada', motivos)
        self.assertIn('Consumo anulado con habitación inconsistente', motivos)
        self.assertIn('Cantidad inválida o faltante en consumo confirmado', motivos)
        self.assertIn('Habitación del consumo inconsistente', motivos)
        self.assertEqual(motivos.count('Importe de consumo inválido'), 3)
        self.assertIn('Estado de consumo desconocido', motivos)
        self.assertTrue(resultado['cuentas'][0]['unidades_incompletas'])

    def test_duplicado_con_estadia_inactiva_no_se_atribuye(self):
        resultado = self.generar([
            pasajero('DUP', '101', 'V1'),
            pasajero('DUP', '102', 'V2', egreso='01/11/2026'),
        ], [consumo('DUP')])
        self.assertEqual(resultado['total_bebidas'], 0)
        self.assertEqual(resultado['cuentas'][0]['detalle'], [])
        self.assertTrue(any('duplicado' in o['motivo'] for o in resultado['observaciones']))

    def test_sin_pasajeros_y_sin_consumos(self):
        self.assertEqual(self.generar([], [])['cuentas'], [])
        resultado = self.generar([pasajero('A', '101', 'V1')], [])
        self.assertEqual(resultado['cuentas'][0]['bebidas'], 0)

    def test_falta_voucher_no_fusiona_cuentas(self):
        resultado = self.generar([pasajero('A', '101', ''), pasajero('B', '101', '')], [])
        self.assertEqual(resultado['cuentas'], [])
        self.assertEqual(len(resultado['observaciones']), 2)


class TestRutaControlCuentas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasajeros = Path(self.tmp.name) / 'pasajeros.csv'
        self.consumos = Path(self.tmp.name) / 'consumos.csv'
        hoy = date.today().strftime('%d/%m/%Y')
        pd.DataFrame([pasajero('A', '101', 'V1', hoy, hoy)]).to_csv(self.pasajeros, index=False)
        pd.DataFrame([consumo('A'), consumo('A', estado='anulado', item='Anulado')]).to_csv(self.consumos, index=False)
        for nombre, archivo in [('DB_PASAJEROS', self.pasajeros), ('DB_CONSUMOS', self.consumos)]:
            p = patch.object(aplicacion, nombre, str(archivo))
            p.start()
            self.addCleanup(p.stop)
        self.cliente = aplicacion.app.test_client()

    def test_ruta_solo_lectura_y_acceso_desde_listado(self):
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        for texto in ('CONTROL PREVENTIVO DE CUENTAS', 'Voucher V1', '$ 100,00', 'Anulado', 'anulado', 'Con consumos'):
            self.assertIn(texto, html)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])
        self.assertIn('/control-cuentas', self.cliente.get('/listado-pasajeros-alojados').get_data(as_text=True))

    def test_dashboard_enlace_unico_en_consumos(self):
        respuesta = self.cliente.get('/dashboard')
        self.assertEqual(respuesta.status_code, 200)
        lector = LectorEnlacesDashboard()
        lector.feed(respuesta.get_data(as_text=True))
        self.assertEqual(len(lector.enlaces), 1)
        enlace = lector.enlaces[0]
        self.assertIn('Chequear Cuentas', enlace['texto'])
        self.assertIn('consumos-panel', enlace['paneles'])
        self.assertNotIn('recepcion-panel', enlace['paneles'])

    def test_archivo_inexistente_vacio_o_columnas_faltantes_reporta_error(self):
        for contenido in (None, '', 'id_estadia\nA\n'):
            with self.subTest(contenido=contenido):
                if contenido is None:
                    self.consumos.unlink(missing_ok=True)
                else:
                    self.consumos.write_text(contenido, encoding='utf-8')
                respuesta = self.cliente.get('/control-cuentas')
                self.assertEqual(respuesta.status_code, 503)
                self.assertIn('No se pudo generar el control de cuentas', respuesta.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
