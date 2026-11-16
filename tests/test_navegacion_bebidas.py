import re
import tempfile
import unittest
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app as aplicacion
from core import consumos, dashboard


class TestNavegacionBebidas(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.pasajeros = str(Path(temporal.name) / 'pasajeros.csv')
        self.consumos = str(Path(temporal.name) / 'consumos.csv')
        hoy = date.today()
        filas = []
        for habitacion, nombre, identificador, egreso, voucher in [
            (101, 'PASAJERO UNO', 'ESTADIA-1', hoy, 'V1'),
            (101, 'PASAJERO DOS', 'ESTADIA-2', hoy, 'V2'),
            (102, 'OTRA HABITACION', 'ESTADIA-3', hoy + timedelta(days=1), 'V3'),
        ]:
            filas.append({
                'Nro. habitación': habitacion,
                'Fecha de ingreso': (hoy - timedelta(days=1)).strftime('%d/%m/%Y'),
                'Fecha de egreso': egreso.strftime('%d/%m/%Y'),
                'Apellido y nombre': nombre,
                'Servicios': 'DESAYUNO',
                'Edad': 40,
                'Voucher': voucher,
                'id_estadia': identificador,
            })
        pd.DataFrame(filas).to_csv(self.pasajeros, index=False)
        self.catalogo = [
            {'codigo': 'agua', 'nombre': 'Agua', 'icono': '', 'precio': 1000,
             'habilitado': True},
            {'codigo': 'sin_precio', 'nombre': 'Sin precio', 'icono': '', 'precio': None,
             'habilitado': False},
        ]
        parches = [
            patch.object(aplicacion, 'obtener_habitaciones_ocupadas',
                         partial(dashboard.obtener_habitaciones_ocupadas, self.pasajeros)),
            patch.object(dashboard, 'obtener_todos_pasajeros_habitacion',
                         partial(dashboard.obtener_todos_pasajeros_habitacion,
                                 archivo_pasajeros=self.pasajeros)),
            patch.object(aplicacion, 'validar_estadia_para_consumo',
                         partial(aplicacion.validar_estadia_para_consumo,
                                 archivo_pasajeros=self.pasajeros)),
            patch.object(aplicacion, 'agregar_consumo_bebida_rapida',
                         partial(consumos.agregar_consumo_bebida_rapida,
                                 archivo_consumos=self.consumos)),
            patch.object(aplicacion, 'obtener_resumen_habitacion',
                         partial(consumos.obtener_resumen_habitacion,
                                 archivo_consumos=self.consumos)),
            patch.object(aplicacion, 'obtener_catalogo_bebidas', return_value=self.catalogo),
            patch.object(consumos, 'obtener_catalogo_bebidas', return_value=self.catalogo),
            patch.object(aplicacion, 'DB_CONSUMOS', self.consumos),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.cliente = aplicacion.app.test_client()

    def test_tablero_preserva_destinos_por_estado(self):
        datos = {
            'pisos': {1: [101, 102, 103, 104, 105]},
            'estados': {101: 'ocupada', 102: 'con_consumos', 103: 'checkout',
                        104: 'vacia', 105: 'reservada'},
            'ocupadas': {numero: {'plazas': 1, 'pasajero': 'PRUEBA'}
                         for numero in (101, 102, 103)},
            'reservadas': {105: {'plazas': 1, 'ingreso': '01/01/2099'}},
            'estadisticas': {'total': 5, 'ocupadas': 3, 'con_consumos': 1,
                             'reservadas': 1, 'vacias': 1, 'checkouts_pendientes': 1},
            'checkouts_hoy': {103},
        }
        with patch.object(aplicacion, 'obtener_datos_dashboard', return_value=datos):
            html = self.cliente.get('/dashboard').get_data(as_text=True)
        for numero in (101, 102, 103):
            self.assertIn(f'href="/bebidas-rapidas?habitacion={numero}"', html)
        self.assertIn('href="/reserva-express?habitacion=104"', html)
        self.assertIn('/reserva-express?habitacion=105&reserva_futura=1', html)

    def test_vista_individual_y_general_y_checkout(self):
        individual = self.cliente.get('/bebidas-rapidas?habitacion=101').get_data(as_text=True)
        self.assertIn('Habitación 101', individual)
        self.assertIn('PASAJERO UNO', individual)
        self.assertIn('PASAJERO DOS', individual)
        self.assertNotIn('OTRA HABITACION', individual)
        self.assertIn('action="/bebidas-rapidas?habitacion=101"', individual)
        self.assertIn('href="/habitacion/101"', individual)
        self.assertIn('href="/checkout/101"', individual)
        self.assertIn('data-producto="sin_precio"', individual)
        self.assertRegex(individual, r'data-precio=""\s+disabled')
        general = self.cliente.get('/bebidas-rapidas').get_data(as_text=True)
        self.assertIn('OTRA HABITACION', general)
        self.assertIn('action="/bebidas-rapidas"', general)
        sin_checkout = self.cliente.get('/bebidas-rapidas?habitacion=102').get_data(as_text=True)
        self.assertNotIn('href="/checkout/102"', sin_checkout)

    def test_precios_visibles_en_cada_boton_sin_tarjeta_de_precios(self):
        for ruta, cantidad, precio, precio_visible in [
            ('/bebidas-rapidas?habitacion=101', 2, 1234.5, '1234.5'),
            ('/bebidas-rapidas', 3, 3500.0, '3500'),
        ]:
            with self.subTest(ruta=ruta):
                self.catalogo[0]['precio'] = precio
                html = self.cliente.get(ruta).get_data(as_text=True)
                self.assertNotIn('Precios configurados', html)
                self.assertNotIn('por unidad', html)
                botones = re.findall(
                    r'<button\b[^>]*data-producto="agua"[^>]*>.*?</button>',
                    html, re.DOTALL,
                )
                self.assertEqual(len(botones), cantidad)
                for boton in botones:
                    self.assertIn(f'<span>${precio_visible}</span>', boton)
                    self.assertIn(f'data-precio="{precio}"', boton)
                botones_sin_precio = re.findall(
                    r'<button\b[^>]*data-producto="sin_precio"[^>]*>.*?</button>',
                    html, re.DOTALL,
                )
                self.assertEqual(len(botones_sin_precio), cantidad)
                for boton in botones_sin_precio:
                    self.assertIn('disabled', boton)
                    self.assertIn('Precio pendiente de configurar', boton)

    def test_cinco_unidades_en_ambas_modalidades(self):
        for ruta, identificador in [
            ('/bebidas-rapidas?habitacion=101', 'ESTADIA-1'),
            ('/bebidas-rapidas', 'ESTADIA-2'),
        ]:
            with self.subTest(ruta=ruta):
                html = self.cliente.get(ruta).get_data(as_text=True)
                self.assertIn('data-cantidad="5">x5</button>', html)
                respuesta = self.cliente.post(ruta, data={
                    'habitacion': '101', 'id_estadia': identificador,
                    'producto': 'agua', 'cantidad': '5',
                })
                self.assertEqual(respuesta.location, ruta)
        registros = pd.read_csv(self.consumos)
        self.assertEqual(registros['id_estadia'].tolist(), ['ESTADIA-1', 'ESTADIA-2'])
        self.assertEqual(registros['cantidad'].tolist(), [5, 5])
        self.assertEqual(registros['monto'].tolist(), [5000, 5000])

    def test_registros_individual_y_general_conservan_estadia_y_contexto(self):
        datos = {'habitacion': '101', 'id_estadia': 'ESTADIA-2',
                 'producto': 'agua', 'cantidad': '2'}
        individual = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(individual.location, '/bebidas-rapidas?habitacion=101')
        general = self.cliente.post('/bebidas-rapidas', data=datos)
        self.assertEqual(general.location, '/bebidas-rapidas')
        registros = pd.read_csv(self.consumos)
        self.assertEqual(registros['id_estadia'].tolist(), ['ESTADIA-2', 'ESTADIA-2'])
        self.assertEqual(registros['monto'].tolist(), [2000, 2000])

    def test_rechaza_estadias_invalidas_y_habitacion_distinta(self):
        datos = {'habitacion': '101', 'id_estadia': 'ESTADIA-3',
                 'producto': 'agua', 'cantidad': '1'}
        respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        self.assertIn('No se pudo validar', self.cliente.get(respuesta.location).get_data(as_text=True))
        datos['habitacion'] = '102'
        respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        datos['habitacion'] = '101'
        datos['id_estadia'] = 'NO-EXISTE'
        respuesta = self.cliente.post('/bebidas-rapidas', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas')
        datos['id_estadia'] = 'ESTADIA-1'
        datos['producto'] = 'sin_precio'
        respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        self.assertIn('todavía no está configurado',
                      self.cliente.get(respuesta.location).get_data(as_text=True))
        self.assertFalse(Path(self.consumos).exists())

    def test_habitacion_invalida_o_sin_estadia_valida_muestra_aviso(self):
        for parametro in ('abc', '999', ''):
            respuesta = self.cliente.get(f'/bebidas-rapidas?habitacion={parametro}')
            self.assertEqual(respuesta.location, '/dashboard')
        filas = pd.read_csv(self.pasajeros)
        filas.loc[filas['Nro. habitación'] == 101, 'id_estadia'] = ''
        filas.to_csv(self.pasajeros, index=False)
        respuesta = self.cliente.get('/bebidas-rapidas?habitacion=101')
        html = respuesta.get_data(as_text=True)
        self.assertIn('no tiene estadías válidas', html)
        self.assertIn('href="/habitacion/101"', html)
        self.assertIn('href="/checkout/101"', html)
        self.assertNotIn('class="passenger-form bebida-masiva-form"', html)

    def test_estadias_invalidas_no_exponen_formulario_y_son_informadas(self):
        filas = pd.read_csv(self.pasajeros)
        filas.loc[filas['id_estadia'] == 'ESTADIA-2', 'id_estadia'] = ''
        filas.to_csv(self.pasajeros, index=False)
        html = self.cliente.get('/bebidas-rapidas?habitacion=101').get_data(as_text=True)
        self.assertIn('Algunos pasajeros no tienen una estadía válida', html)
        self.assertIn('PASAJERO UNO', html)
        self.assertNotIn('PASAJERO DOS', html)

    def test_ficha_conserva_funciones_administrativas(self):
        self.cliente.post('/bebidas-rapidas?habitacion=101', data={
            'habitacion': '101', 'id_estadia': 'ESTADIA-1',
            'producto': 'agua', 'cantidad': '1',
        })
        html = self.cliente.get('/habitacion/101').get_data(as_text=True)
        for texto in ('Información de la Reserva', 'Consumos Registrados',
                      'Resumen de Consumos por Pasajero', 'Motivo obligatorio',
                      'PASAJERO UNO', 'PASAJERO DOS', 'href="/bebidas-rapidas?habitacion=101"',
                      '/cambiar-habitacion/101', '/cambiar-habitacion-parcial/101',
                      '/checkout/101'):
            self.assertIn(texto, html)
        self.assertNotIn('id="form-bebida-rapida"', html)


if __name__ == '__main__':
    unittest.main()
