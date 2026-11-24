import re
import tempfile
import unittest
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from werkzeug.datastructures import MultiDict

import app as aplicacion
from core import consumos, dashboard
from core.consumos import obtener_catalogo_bebidas as cargar_catalogo_real


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
            patch.object(aplicacion, 'agregar_consumos_bebidas_multiples',
                         partial(consumos.agregar_consumos_bebidas_multiples,
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

    def test_catalogo_invalido_informa_y_bloquea_las_cargas(self):
        archivo_catalogo = Path(self.pasajeros).parent / 'catalogo.csv'
        historico = b'id_consumo,habitacion,monto\nexistente,101,500\n'
        Path(self.consumos).write_bytes(historico)
        casos = [
            (None, 'No se encontró'),
            ('codigo,producto\nagua,Agua\n', 'faltan columnas'),
            ('codigo,producto,categoria,sector,precio_actual\n'
             'agua,Uno,aguas,Prueba,1\n AGUA ,Dos,aguas,Prueba,2\n', 'duplicados'),
        ]
        with patch.object(consumos, 'RUTA_CATALOGO_PRODUCTOS', archivo_catalogo), \
                patch.object(consumos, 'obtener_catalogo_bebidas', wraps=cargar_catalogo_real), \
                patch.object(aplicacion, 'obtener_catalogo_bebidas', wraps=cargar_catalogo_real):
            for contenido, mensaje in casos:
                with self.subTest(mensaje=mensaje):
                    if contenido is None:
                        archivo_catalogo.unlink(missing_ok=True)
                    else:
                        archivo_catalogo.write_text(contenido, encoding='utf-8')
                    respuesta = self.cliente.get('/bebidas-rapidas?habitacion=101')
                    html = respuesta.get_data(as_text=True)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertIn(mensaje, html)
                    self.assertNotIn('data-producto="agua"', html)
                    for modo in ('individual', 'carga_multiple'):
                        datos = {
                            'habitacion': '101', 'producto': 'agua', 'cantidad': '1',
                            'id_estadia': 'ESTADIA-1', 'modo': modo,
                        }
                        respuesta = self.cliente.post(
                            '/bebidas-rapidas?habitacion=101',
                            data=datos, follow_redirects=True,
                        )
                        self.assertEqual(respuesta.status_code, 200)
                        self.assertIn(mensaje, respuesta.get_data(as_text=True))
                        self.assertEqual(Path(self.consumos).read_bytes(), historico)

    def test_botoneras_y_resumen_multiple_por_habitacion(self):
        for ruta, habitaciones in [
            ('/bebidas-rapidas?habitacion=101', ['101']),
            ('/bebidas-rapidas', ['101', '102']),
        ]:
            with self.subTest(ruta=ruta):
                html = self.cliente.get(ruta).get_data(as_text=True)
                self.assertIn('class="passenger-form bebida-masiva-form"', html)
                self.assertIn('data-cantidad="5">x5</button>', html)
                self.assertIn('mantenga Ctrl y haga clic', html)
                formularios = re.findall(
                    r'<form class="carga-multiple-form\b.*?</form>', html, re.DOTALL
                )
                self.assertEqual(len(formularios), len(habitaciones))
                for formulario, habitacion in zip(formularios, habitaciones):
                    self.assertIn('Carga múltiple', html)
                    self.assertIn(f'action="{ruta}"', formulario)
                    self.assertIn('name="modo" value="carga_multiple"', formulario)
                    self.assertIn(f'name="habitacion" value="{habitacion}"', formulario)
                    self.assertEqual(
                        re.findall(r'\bname="([^"]+)"', formulario),
                        ['modo', 'habitacion', 'producto', 'cantidad', 'id_estadia'],
                    )
                    self.assertIn('class="plantilla-fila-multiple"', formulario)
                    self.assertNotIn('pasajero-predeterminado', formulario)
                    self.assertNotIn('producto-multiple', formulario)
                    self.assertIn('Confirmar carga', formulario)

    def test_envio_multiple_conserva_orden_de_los_campos_repetidos(self):
        datos = MultiDict([
            ('modo', 'carga_multiple'), ('habitacion', '101'),
            ('producto', 'agua'), ('cantidad', '1'), ('id_estadia', 'ESTADIA-1'),
            ('producto', 'agua'), ('cantidad', '2'), ('id_estadia', 'ESTADIA-2'),
            ('producto', 'agua'), ('cantidad', '3'), ('id_estadia', 'ESTADIA-1'),
        ])
        respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        registros = pd.read_csv(self.consumos)
        self.assertEqual(registros['cantidad'].tolist(), [1, 2, 3])
        self.assertEqual(registros['id_estadia'].tolist(),
                         ['ESTADIA-1', 'ESTADIA-2', 'ESTADIA-1'])
        self.assertEqual(registros['pasajero'].tolist(),
                         ['PASAJERO UNO', 'PASAJERO DOS', 'PASAJERO UNO'])

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

    def test_carga_multiple_valida_guarda_una_vez_y_usa_nombres_verificados(self):
        for ruta, estadias in [
            ('/bebidas-rapidas?habitacion=101', ['ESTADIA-1', 'ESTADIA-2']),
            ('/bebidas-rapidas', ['ESTADIA-2', 'ESTADIA-1', 'ESTADIA-2']),
            ('/bebidas-rapidas', ['ESTADIA-1']),
        ]:
            with self.subTest(ruta=ruta):
                datos = {
                    'modo': 'carga_multiple', 'habitacion': '101',
                    'producto': ['agua'] * len(estadias),
                    'cantidad': ['2'] * len(estadias),
                    'id_estadia': estadias,
                    'pasajero': ['NOMBRE FALSO'] * len(estadias),
                }
                with patch.object(
                    aplicacion, 'agregar_consumos_bebidas_multiples',
                    wraps=aplicacion.agregar_consumos_bebidas_multiples,
                ) as guardar:
                    respuesta = self.cliente.post(ruta, data=datos)
                self.assertEqual(respuesta.location, ruta)
                guardar.assert_called_once()
                habitacion, items = guardar.call_args.args
                self.assertEqual(habitacion, 101)
                self.assertEqual([item['id_estadia'] for item in items], estadias)
                self.assertEqual(
                    [item['pasajero'] for item in items],
                    ['PASAJERO UNO' if estadia == 'ESTADIA-1' else 'PASAJERO DOS'
                     for estadia in estadias],
                )
                with self.cliente.session_transaction() as sesion:
                    self.assertEqual(sesion['_flashes'][-1][0], 'success')

        registros = pd.read_csv(self.consumos)
        self.assertEqual(len(registros), 6)
        self.assertEqual(registros['monto'].tolist(), [2000] * 6)
        self.assertNotIn('NOMBRE FALSO', registros['pasajero'].tolist())

    def test_estadia_invalida_cancela_lote_sin_guardar(self):
        datos = {
            'modo': 'carga_multiple', 'habitacion': '101',
            'producto': ['agua', 'agua'], 'cantidad': ['1', '1'],
            'id_estadia': ['ESTADIA-1', 'ESTADIA-3'],
        }
        contenido = b'habitacion,monto\n101,500\n'
        Path(self.consumos).write_bytes(contenido)
        with patch.object(aplicacion, 'agregar_consumos_bebidas_multiples') as guardar:
            respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        guardar.assert_not_called()
        self.assertEqual(Path(self.consumos).read_bytes(), contenido)
        self.assertIn('No se pudo validar',
                      self.cliente.get(respuesta.location).get_data(as_text=True))

    def test_lote_incompleto_o_fuera_de_limites_no_se_guarda(self):
        base = {
            'modo': 'carga_multiple', 'habitacion': '101',
            'producto': ['agua', 'agua'], 'cantidad': ['1', '1'],
            'id_estadia': ['ESTADIA-1', 'ESTADIA-2'],
        }
        casos = [
            {**base, 'producto': []},
            {**base, 'producto': ['agua'] * 4, 'cantidad': ['1'] * 4,
             'id_estadia': ['ESTADIA-1'] * 4},
            {**base, 'cantidad': ['1']},
            {**base, 'id_estadia': ['ESTADIA-1']},
            {**base, 'producto': ['agua', ' ']},
            {**base, 'cantidad': ['1', ' ']},
            {**base, 'id_estadia': ['ESTADIA-1', ' ']},
        ]
        with patch.object(aplicacion, 'agregar_consumos_bebidas_multiples') as guardar:
            for datos in casos:
                with self.subTest(datos=datos):
                    respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
                    self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
                    self.assertIn('Debe seleccionar entre 1 y 3 productos',
                                  self.cliente.get(respuesta.location).get_data(as_text=True))
            guardar.assert_not_called()
        self.assertFalse(Path(self.consumos).exists())

    def test_lote_rechaza_habitacion_no_ocupada_o_distinta_de_pantalla(self):
        datos = {
            'modo': 'carga_multiple', 'habitacion': '102',
            'producto': ['agua'], 'cantidad': ['1'], 'id_estadia': ['ESTADIA-3'],
        }
        with patch.object(aplicacion, 'agregar_consumos_bebidas_multiples') as guardar:
            respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
            self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
            self.assertIn('no corresponde a la pantalla',
                          self.cliente.get(respuesta.location).get_data(as_text=True))
            datos['habitacion'] = '999'
            respuesta = self.cliente.post('/bebidas-rapidas', data=datos)
            self.assertEqual(respuesta.location, '/bebidas-rapidas')
            self.assertIn('no está ocupada',
                          self.cliente.get(respuesta.location).get_data(as_text=True))
            guardar.assert_not_called()

    def test_fallo_de_guardado_multiple_muestra_error(self):
        datos = {
            'modo': 'carga_multiple', 'habitacion': '101',
            'producto': ['agua'], 'cantidad': ['1'], 'id_estadia': ['ESTADIA-1'],
        }
        with patch.object(aplicacion, 'agregar_consumos_bebidas_multiples',
                          return_value=(False, 'Error al guardar')) as guardar:
            respuesta = self.cliente.post('/bebidas-rapidas', data=datos)
        guardar.assert_called_once()
        self.assertEqual(respuesta.location, '/bebidas-rapidas')
        with self.cliente.session_transaction() as sesion:
            self.assertIn(('danger', 'Error al guardar'), sesion['_flashes'])

    def test_cantidad_invalida_no_guarda_ningun_producto_del_lote(self):
        datos = {
            'modo': 'carga_multiple', 'habitacion': '101',
            'producto': ['agua', 'agua'], 'cantidad': ['1', '0'],
            'id_estadia': ['ESTADIA-1', 'ESTADIA-2'],
        }
        respuesta = self.cliente.post('/bebidas-rapidas?habitacion=101', data=datos)
        self.assertEqual(respuesta.location, '/bebidas-rapidas?habitacion=101')
        self.assertIn('cantidad debe ser un entero mayor a cero',
                      self.cliente.get(respuesta.location).get_data(as_text=True))
        self.assertFalse(Path(self.consumos).exists())

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
