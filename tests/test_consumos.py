import tempfile
import unittest
import csv
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core.consumos import (
    ErrorCatalogo,
    agregar_consumo_bebida_rapida,
    agregar_consumos_bebidas_multiples,
    obtener_catalogo_bebidas,
    obtener_consumos_habitacion,
    obtener_total_consumos,
)


class TestConsumos(unittest.TestCase):

    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.catalogo = Path(temporal.name) / 'catalogo.csv'
        self.catalogo.write_text(
            'codigo,producto,categoria,sector,precio_actual\n'
            'bebida_prueba,Bebida de prueba,gaseosas,Prueba,123\n'
            'cafe_prueba,Cafe de prueba,cafeteria,Prueba,45\n'
            'sabor_prueba_a,Sabor A,aguas_saborizadas,Prueba,33\n'
            'sabor_prueba_b,Sabor B,aguas_saborizadas,Prueba,44\n',
            encoding='utf-8',
        )
        parche = patch('core.consumos.RUTA_CATALOGO_PRODUCTOS', self.catalogo)
        parche.start()
        self.addCleanup(parche.stop)

    def test_iconos_de_cafe_y_aguas_saborizadas(self):
        catalogo = {producto['codigo']: producto for producto in obtener_catalogo_bebidas()}
        self.assertEqual(catalogo['cafe_prueba']['icono'], '☕')
        self.assertEqual(catalogo['sabor_prueba_a']['icono'], '🧃')
        self.assertEqual(catalogo['sabor_prueba_b']['icono'], '🧃')

    def test_catalogo_invalido_rechaza_ambas_cargas_sin_modificar_historico(self):
        cabecera = b'codigo,producto,categoria,sector,precio_actual\n'
        casos = [
            (None, 'No se encontró'),
            (b'', 'está vacío'),
            (cabecera, 'no contiene productos'),
            (b'codigo,producto\nprueba,Producto\n', 'faltan columnas'),
            (b'codigo,producto,categoria,sector,precio_actual,codigo\n', 'columnas duplicadas'),
            (cabecera + b'prueba,Uno,gaseosas,Prueba\n', 'fila incompleta'),
            (cabecera + b'prueba,Uno,gaseosas,Prueba,1,extra\n', 'fila incompleta'),
            (cabecera + b'prueba,Uno,gaseosas,Prueba,1\n PRUEBA ,Dos,aguas,Prueba,2\n', 'duplicados'),
            (cabecera + b' ,Uno,gaseosas,Prueba,1\n', 'códigos vacíos'),
            (cabecera + b'prueba,"sin cerrar,gaseosas,Prueba,1\n', 'No se pudo leer'),
            (cabecera + b'prueba,\xff,gaseosas,Prueba,1\n', 'No se pudo leer'),
        ]
        archivo = self.catalogo.parent / 'historico.csv'
        original = b'id_consumo,habitacion,monto\nexistente,101,500\n'
        archivo.write_bytes(original)
        item = {'producto_codigo': 'prueba', 'cantidad': 1,
                'pasajero': 'ANA', 'id_estadia': 'A'}
        for contenido, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                if contenido is None:
                    self.catalogo.unlink()
                else:
                    self.catalogo.write_bytes(contenido)
                with self.assertRaisesRegex(ErrorCatalogo, mensaje):
                    obtener_catalogo_bebidas()
                individual = agregar_consumo_bebida_rapida(
                    101, 'prueba', 1, 'ANA', archivo_consumos=archivo,
                )
                multiple = agregar_consumos_bebidas_multiples(101, [item], archivo)
                for exito, error in (individual, multiple):
                    self.assertFalse(exito)
                    self.assertIn(mensaje, error)
                self.assertEqual(archivo.read_bytes(), original)
                self.assertFalse(Path(str(archivo) + '.lock').exists())

    def test_catalogo_conserva_orden_y_codigo_numerico(self):
        self.catalogo.write_text(
            'codigo,producto,categoria,sector,precio_actual\n'
            '001,Primero,gaseosas,Prueba,1\n'
            '002,Segundo,aguas,Prueba,2\n',
            encoding='utf-8',
        )
        self.assertEqual(
            [producto['codigo'] for producto in obtener_catalogo_bebidas()],
            ['001', '002'],
        )

    def test_precios_no_finitos_quedan_deshabilitados(self):
        self.catalogo.write_text(
            'codigo,producto,categoria,sector,precio_actual\n'
            'infinito,Infinito,gaseosas,Prueba,inf\n'
            'sin_precio,Sin precio,aguas,Prueba,\n'
            'gratis,Gratis,aguas,Prueba,0\n',
            encoding='utf-8',
        )
        catalogo = {producto['codigo']: producto for producto in obtener_catalogo_bebidas()}
        self.assertFalse(catalogo['infinito']['habilitado'])
        self.assertFalse(catalogo['sin_precio']['habilitado'])
        self.assertTrue(catalogo['gratis']['habilitado'])

    def test_agregar_bebida_con_cantidad_y_precio_correctos(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = str(Path(tmp) / "consumos_prueba.csv")

            exito, mensaje = agregar_consumo_bebida_rapida(
                num_habitacion=999,
                producto_codigo="bebida_prueba",
                cantidad=2,
                pasajero="PASAJERO DE PRUEBA",
                archivo_consumos=archivo,
            )

            self.assertTrue(exito, mensaje)

            consumos = obtener_consumos_habitacion(999, archivo)

            self.assertEqual(len(consumos), 1)
            self.assertEqual(consumos.iloc[0]["item"], "Bebida de prueba")
            self.assertEqual(int(consumos.iloc[0]["cantidad"]), 2)
            self.assertEqual(float(consumos.iloc[0]["precio_unitario"]), 123.0)
            self.assertEqual(float(consumos.iloc[0]["monto"]), 246.0)

            totales = obtener_total_consumos(999, archivo)
            self.assertEqual(float(totales["total"]), 246.0)

    def test_cantidad_cero_no_debe_generar_consumo(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = str(Path(tmp) / "consumos_prueba.csv")

            exito, mensaje = agregar_consumo_bebida_rapida(
                num_habitacion=999,
                producto_codigo="bebida_prueba",
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

    def test_carga_multiple_conserva_historico_y_asigna_ids_por_pasajero(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            archivo.write_text(
                'id_consumo,id_estadia,habitacion,monto,extra\n'
                '000123,00105,105,100,valor anterior\n'
                ',ANTERIOR,105,200,otro valor\n',
                encoding='utf-8',
            )
            items = [
                {'producto_codigo': 'bebida_prueba', 'cantidad': '2',
                 'pasajero': 'ANA', 'id_estadia': 'ESTADIA-A'},
                {'producto_codigo': 'cafe_prueba', 'cantidad': 1,
                 'pasajero': 'LUIS', 'id_estadia': 'ESTADIA-B'},
                {'producto_codigo': 'bebida_prueba', 'cantidad': 3,
                 'pasajero': 'ANA', 'id_estadia': 'ESTADIA-A'},
            ]
            with patch('core.consumos.os.replace', wraps=os.replace) as reemplazo:
                exito, mensaje = agregar_consumos_bebidas_multiples(105, items, archivo)
            self.assertTrue(exito, mensaje)
            reemplazo.assert_called_once()

            with archivo.open(encoding='utf-8', newline='') as fuente:
                filas = list(csv.DictReader(fuente))
            self.assertEqual(len(filas), 5)
            self.assertEqual(filas[0]['id_consumo'], '000123')
            self.assertEqual(filas[0]['id_estadia'], '00105')
            self.assertEqual([fila['extra'] for fila in filas[:2]], ['valor anterior', 'otro valor'])
            self.assertTrue(filas[1]['id_consumo'])
            self.assertEqual(len({fila['id_consumo'] for fila in filas}), 5)
            self.assertEqual([fila['id_estadia'] for fila in filas[2:]],
                             ['ESTADIA-A', 'ESTADIA-B', 'ESTADIA-A'])
            self.assertEqual([fila['pasajero'] for fila in filas[2:]], ['ANA', 'LUIS', 'ANA'])
            self.assertEqual(float(filas[2]['monto']), 246)
            self.assertEqual(filas[4]['cantidad'], '3')

    def test_carga_multiple_de_dos_bebidas_en_archivo_nuevo(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            items = [
                {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                 'pasajero': 'ANA', 'id_estadia': 'A'},
                {'producto_codigo': 'cafe_prueba', 'cantidad': 2,
                 'pasajero': 'LUIS', 'id_estadia': 'B'},
            ]
            exito, mensaje = agregar_consumos_bebidas_multiples(105, items, archivo)
            self.assertTrue(exito, mensaje)
            with archivo.open(encoding='utf-8', newline='') as fuente:
                filas = list(csv.DictReader(fuente))
            self.assertEqual(len(filas), 2)
            self.assertEqual([fila['id_estadia'] for fila in filas], ['A', 'B'])
            self.assertNotEqual(filas[0]['id_consumo'], filas[1]['id_consumo'])

    def test_lote_invalido_no_modifica_historico_ni_crea_archivo(self):
        valido = {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                  'pasajero': 'ANA', 'id_estadia': 'A'}
        invalidos = [
            {**valido, 'cantidad': cantidad}
            for cantidad in (0, -1, 'abc', 1.5, True)
        ] + [{**valido, 'producto_codigo': 'inexistente'}, {'cantidad': 1}]
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            contenido = b'habitacion,monto\n105,500\n'
            for invalido in invalidos:
                for existe in (False, True):
                    with self.subTest(invalido=invalido, existe=existe):
                        if existe:
                            archivo.write_bytes(contenido)
                        elif archivo.exists():
                            archivo.unlink()
                        exito, mensaje = agregar_consumos_bebidas_multiples(
                            105, [valido, invalido], archivo,
                        )
                        self.assertFalse(exito, mensaje)
                        if existe:
                            self.assertEqual(archivo.read_bytes(), contenido)
                        else:
                            self.assertFalse(archivo.exists())

    def test_pasajero_o_estadia_vacios_rechazan_lote_sin_modificar_archivo(self):
        valido = {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                  'pasajero': 'ANA', 'id_estadia': 'A'}
        contenido = b'id_consumo,habitacion,monto\n,105,500\n'
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            for campo in ('pasajero', 'id_estadia'):
                for valor in ('', ' \t\n '):
                    for existe in (False, True):
                        with self.subTest(campo=campo, valor=valor, existe=existe):
                            if existe:
                                archivo.write_bytes(contenido)
                            elif archivo.exists():
                                archivo.unlink()
                            invalido = {**valido, campo: valor}
                            exito, mensaje = agregar_consumos_bebidas_multiples(
                                105, [valido, invalido], archivo,
                            )
                            self.assertFalse(exito, mensaje)
                            if existe:
                                self.assertEqual(archivo.read_bytes(), contenido)
                            else:
                                self.assertFalse(archivo.exists())

    def test_precio_no_configurado_no_registra_lote(self):
        item = {'producto_codigo': 'sin_precio', 'cantidad': 1,
                'pasajero': 'ANA', 'id_estadia': 'A'}
        catalogo = [{'codigo': 'sin_precio', 'nombre': 'Bebida',
                     'habilitado': False, 'precio': None}]
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            with patch('core.consumos.obtener_catalogo_bebidas', return_value=catalogo):
                exito, mensaje = agregar_consumos_bebidas_multiples(105, [item], archivo)
            self.assertFalse(exito)
            self.assertIn('precio', mensaje)
            self.assertFalse(archivo.exists())

    def test_historico_malformado_no_se_sobrescribe(self):
        item = {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                'pasajero': 'ANA', 'id_estadia': 'A'}
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            for contenido in (b'habitacion,monto\n105\n', b'habitacion,monto\n105,500,extra\n'):
                with self.subTest(contenido=contenido):
                    archivo.write_bytes(contenido)
                    exito, mensaje = agregar_consumos_bebidas_multiples(105, [item], archivo)
                    self.assertFalse(exito, mensaje)
                    self.assertEqual(archivo.read_bytes(), contenido)

    def test_fallo_al_reemplazar_no_modifica_historico_y_limpia_temporal(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            contenido = b'habitacion,monto\n105,500\n'
            archivo.write_bytes(contenido)
            item = {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                    'pasajero': 'ANA', 'id_estadia': 'A'}
            with patch('core.consumos.os.replace', side_effect=OSError('disco')):
                exito, mensaje = agregar_consumos_bebidas_multiples(105, [item], archivo)
            self.assertFalse(exito)
            self.assertIn('disco', mensaje)
            self.assertEqual(archivo.read_bytes(), contenido)
            self.assertEqual(set(Path(tmp).iterdir()), {archivo, Path(str(archivo) + '.lock')})

    def test_limites_del_lote_y_habitacion_invalida(self):
        item = {'producto_codigo': 'bebida_prueba', 'cantidad': 1,
                'pasajero': 'ANA', 'id_estadia': 'A'}
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / 'consumos.csv'
            for habitacion, items in [(105, []), (105, [item] * 4),
                                      (105, None), (0, [item]), ('x', [item])]:
                with self.subTest(habitacion=habitacion, items=items):
                    exito, mensaje = agregar_consumos_bebidas_multiples(
                        habitacion, items, archivo,
                    )
                    self.assertFalse(exito, mensaje)
                    self.assertFalse(archivo.exists())


if __name__ == "__main__":
    unittest.main()
