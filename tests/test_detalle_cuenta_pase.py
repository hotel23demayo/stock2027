import tempfile
import unittest
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from flask import template_rendered

import app as aplicacion
from core.pase_caja import COLUMNAS_CONSUMOS


class LectorEnlaces(HTMLParser):
    def __init__(self):
        super().__init__()
        self.enlaces = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == 'a' and atributos.get('href', '').startswith('/pase-turno/detalle?'):
            self.enlaces.append(atributos['href'])


class TestDetalleCuentaPase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasajeros = Path(self.tmp.name) / 'pasajeros.csv'
        self.consumos = Path(self.tmp.name) / 'consumos.csv'
        hoy = date.today()
        filas = []
        for identificador, habitacion, voucher, egreso in [
            ('A', '101', 'A & 1', hoy), ('B', '101', 'A & 1', hoy),
            ('C', '101', 'B', hoy), ('D', '102', 'A & 1', hoy),
            ('E', '103', 'FUTURO', hoy + timedelta(days=1)),
            ('F', '104', '', hoy), ('DUP', '105', 'X', hoy),
            ('DUP', '106', 'Y', hoy),
        ]:
            filas.append({
                'id_estadia': identificador, 'Nro. habitación': habitacion,
                'Voucher': voucher, 'Apellido y nombre': 'TITULAR ' + identificador,
                'Fecha de ingreso': (hoy - timedelta(days=3)).strftime('%d/%m/%Y'),
                'Fecha de egreso': egreso.strftime('%d/%m/%Y')
            })
        pd.DataFrame(filas).to_csv(self.pasajeros, index=False)
        consumos = []

        def agregar(identificador, habitacion, item, monto, estado='vigente',
                    fecha='10/11/2026 10:00', categoria='Bebidas'):
            consumos.append({
                'id_consumo': 'C-' + item, 'id_estadia': identificador,
                'fecha': fecha, 'habitacion': habitacion, 'pasajero': identificador,
                'categoria': categoria, 'item': item, 'cantidad': '1',
                'precio_unitario': monto, 'monto': monto, 'estado': estado,
                'fecha_anulacion': '', 'motivo_anulacion': '',
            })

        agregar('A', '101', 'Agua tardía', '1500', fecha='11/11/2026 10:00')
        agregar('B', '101', 'Agua temprana', '2500', fecha='09/11/2026 13:15')
        agregar('A', '101', 'Agua hora anterior', '500', fecha='11/11/2026 08:00')
        agregar('C', '101', 'Otra cuenta', '3000')
        agregar('D', '102', 'Otra habitación', '4000')
        agregar('A', '101', 'Anulada', '9999', estado='anulado')
        agregar('', '101', 'Pendiente', '9999')
        agregar('A', '102', 'Habitación incorrecta', '9999')
        agregar('A', '101', 'Estado desconocido', '9999', estado='pendiente')
        agregar('A', '101', 'Importe inválido', 'nan')
        agregar('A', '101', 'Otra categoría', '9999', categoria='Comida')
        agregar('E', '103', 'Futura', '9999')
        agregar('DUP', '105', 'Identificador duplicado', '9999')
        pd.DataFrame(consumos, columns=COLUMNAS_CONSUMOS).to_csv(self.consumos, index=False)
        for nombre, archivo in [('DB_PASAJEROS', self.pasajeros), ('DB_CONSUMOS', self.consumos)]:
            parche = patch.object(aplicacion, nombre, str(archivo))
            parche.start()
            self.addCleanup(parche.stop)
        self.cliente = aplicacion.app.test_client()

    def obtener_contexto(self, ruta, query_string=None):
        capturas = []

        def capturar(sender, template, context, **extra):
            capturas.append((template.name, context))

        template_rendered.connect(capturar, aplicacion.app, weak=False)
        try:
            respuesta = self.cliente.get(ruta, query_string=query_string)
        finally:
            template_rendered.disconnect(capturar, aplicacion.app)
        return respuesta, capturas

    def test_detalles_separados_y_totales_identicos_al_pase(self):
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        pase, capturas = self.obtener_contexto('/pase-turno')
        self.assertEqual(pase.status_code, 200)
        cuentas = capturas[0][1]['cuentas']
        lector = LectorEnlaces()
        lector.feed(pase.get_data(as_text=True))
        self.assertEqual(len(lector.enlaces), len(cuentas))
        self.assertEqual(len(cuentas), 6)
        for enlace, cuenta in zip(lector.enlaces, cuentas):
            respuesta, detalle = self.obtener_contexto(enlace)
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(detalle[0][1]['cuenta']['bebidas'], cuenta['bebidas'])

        respuesta, detalle = self.obtener_contexto('/pase-turno/detalle', {
            'habitacion': '101', 'voucher': 'A & 1'
        })
        html = respuesta.get_data(as_text=True)
        self.assertIn('COMPROBANTE INFORMATIVO - NO FISCAL', html)
        self.assertIn('TITULAR A', html)
        self.assertIn('@page { size: A4 portrait; margin: 15mm; }', html)
        self.assertIn('.acciones { display: none; }', html)
        self.assertIn('Imprimir detalle', html)
        self.assertIn('Volver al Pase de Turno', html)
        self.assertIn('$ 4.500', html)
        self.assertEqual([c['item'] for c in detalle[0][1]['consumos']],
                         ['Agua temprana', 'Agua hora anterior', 'Agua tardía'])
        for texto in ('Otra cuenta', 'Otra habitación', 'Anulada', 'Pendiente',
                      'Habitación incorrecta', 'Estado desconocido', 'Importe inválido',
                      'Otra categoría', 'Futura', 'Identificador duplicado'):
            self.assertNotIn(texto, html)
        for habitacion, voucher, propio, ajeno, total in [
            ('101', 'B', 'Otra cuenta', 'Agua tardía', '$ 3.000'),
            ('102', 'A & 1', 'Otra habitación', 'Otra cuenta', '$ 4.000'),
        ]:
            respuesta = self.cliente.get('/pase-turno/detalle', query_string={
                'habitacion': habitacion, 'voucher': voucher
            })
            html = respuesta.get_data(as_text=True)
            self.assertIn(propio, html)
            self.assertNotIn(ajeno, html)
            self.assertIn(total, html)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

    def test_rechaza_cuentas_ajenas_a_salidas_y_parametros_incompletos(self):
        for query in (
            {}, {'habitacion': '101'}, {'voucher': 'B'},
            {'habitacion': '101', 'voucher': 'inexistente'},
            {'habitacion': '103', 'voucher': 'FUTURO'},
            {'habitacion': '102', 'voucher': 'B'},
        ):
            with self.subTest(query=query):
                self.assertEqual(self.cliente.get('/pase-turno/detalle', query_string=query).status_code, 404)

    def test_cuenta_sin_consumos_y_voucher_vacio(self):
        respuesta = self.cliente.get('/pase-turno/detalle', query_string={
            'habitacion': '104', 'voucher': ''
        })
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        self.assertIn('No hay bebidas confirmadas para esta cuenta.', html)
        self.assertIn('$ 0', html)

    def test_cuenta_retirada_deja_de_ser_accesible(self):
        url = '/pase-turno/detalle?habitacion=101&voucher=B'
        self.assertEqual(self.cliente.get(url).status_code, 200)
        padron = pd.read_csv(self.pasajeros, dtype=str, keep_default_na=False)
        padron = padron[padron['id_estadia'] != 'C']
        padron.to_csv(self.pasajeros, index=False)
        self.assertEqual(self.cliente.get(url).status_code, 404)

    def test_importe_con_decimales_coincide_en_pase_y_detalle(self):
        datos = pd.read_csv(self.consumos, dtype=str, keep_default_na=False)
        datos.loc[datos['item'] == 'Otra cuenta', 'monto'] = '3000.25'
        datos.to_csv(self.consumos, index=False)
        pase = self.cliente.get('/pase-turno').get_data(as_text=True)
        detalle = self.cliente.get('/pase-turno/detalle', query_string={
            'habitacion': '101', 'voucher': 'B'
        }).get_data(as_text=True)
        self.assertIn('$ 3.000,25', pase)
        self.assertIn('$ 3.000,25', detalle)


if __name__ == '__main__':
    unittest.main()
