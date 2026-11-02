import tempfile
import unittest
from pathlib import Path


import pandas as pd
from core.pase_caja import obtener_pasajeros_con_salida
from core.pase_caja import leer_pasajeros, leer_consumos
from core.pase_caja import vincular_consumos_bebidas


class TestLecturaPaseCaja(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()


    def test_leer_pasajeros(self):
        archivo = self.base / 'pasajeros.csv'

        pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104',
            'Apellido y nombre': 'JUAN GOMEZ',
            'Fecha de ingreso': '28/10/2026',
            'Fecha de egreso': '01/11/2026',
            'Voucher': 'V-001'
        }]).to_csv(archivo, index=False)

        df = leer_pasajeros(archivo)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['id_estadia'], 'EST-001')
        self.assertEqual(df.iloc[0]['Nro. habitación'], '104')

    def test_leer_consumos(self):
        archivo = self.base / 'consumos.csv'

        pd.DataFrame([{
            'id_consumo': 'CON-001',
            'id_estadia': 'EST-001',
            'fecha': '01/11/2026',
            'habitacion': '104',
            'pasajero': 'JUAN GOMEZ',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'cantidad': '2',
            'precio_unitario': '1500',
            'monto': '3000',
            'estado': 'vigente'
        }]).to_csv(archivo, index=False)

        df = leer_consumos(archivo)

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['id_estadia'], 'EST-001')
        self.assertEqual(df.iloc[0]['monto'], '3000')

    def test_archivo_inexistente(self):
        archivo = self.base / 'inexistente.csv'

        df = leer_pasajeros(archivo)

        self.assertTrue(df.empty)
        self.assertIn('id_estadia', df.columns)

        df = leer_consumos(archivo)

        self.assertTrue(df.empty)
        self.assertIn('id_consumo', df.columns)
    def test_lectura_no_modifica_archivo(self):
        archivo = self.base / 'pasajeros.csv'

        contenido_original = (
            'id_estadia,habitacion,apellido,nombre,ingreso,egreso,voucher\n'
            'EST-001,104,GOMEZ,JUAN,28/10/2026,01/11/2026,V-001\n'
        )

        archivo.write_text(contenido_original, encoding='utf-8')

        leer_pasajeros(archivo)

        contenido_final = archivo.read_text(encoding='utf-8')

        self.assertEqual(contenido_original, contenido_final)
        
    def test_filtrar_salidas_del_dia(self):
        pasajeros = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '104',
                'Apellido y nombre': 'JUAN GOMEZ',
                'Fecha de ingreso': '28/10/2026',
                'Fecha de egreso': '01/11/2026',
                'Voucher': 'V-001'
            },
            {
                'id_estadia': 'EST-002',
                'Nro. habitación': '105',
                'Apellido y nombre': 'ANA PEREZ',
                'Fecha de ingreso': '29/10/2026',
                'Fecha de egreso': '02/11/2026',
                'Voucher': 'V-002'
            }
        ])

        resultado = obtener_pasajeros_con_salida(
            pasajeros,
            '01/11/2026'
        )

        self.assertEqual(len(resultado), 1)
        self.assertEqual(
            resultado.iloc[0]['id_estadia'],
            'EST-001'
        )

    def test_excluir_fechas_invalidas(self):
        pasajeros = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '104',
                'Apellido y nombre': 'JUAN GOMEZ',
                'Fecha de ingreso': 'fecha incorrecta',
                'Fecha de egreso': '01/11/2026',
                'Voucher': 'V-001'
            },
            {
                'id_estadia': 'EST-002',
                'Nro. habitación': '105',
                'Apellido y nombre': 'ANA PEREZ',
                'Fecha de ingreso': '28/10/2026',
                'Fecha de egreso': 'fecha incorrecta',
                'Voucher': 'V-002'
            }
        ])

        resultado = obtener_pasajeros_con_salida(
            pasajeros,
            '01/11/2026'
        )

        self.assertTrue(resultado.empty)

    def test_excluir_estadias_sin_identificador(self):
        pasajeros = pd.DataFrame([{
            'id_estadia': '',
            'Nro. habitación': '104',
            'Apellido y nombre': 'JUAN GOMEZ',
            'Fecha de ingreso': '28/10/2026',
            'Fecha de egreso': '01/11/2026',
            'Voucher': 'V-001'
        }])

        resultado = obtener_pasajeros_con_salida(
            pasajeros,
            '01/11/2026'
        )

        self.assertTrue(resultado.empty)
        
    def test_filtro_no_modifica_dataframe_original(self):
        pasajeros = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104',
            'Apellido y nombre': 'JUAN GOMEZ',
            'Fecha de ingreso': '28/10/2026',
            'Fecha de egreso': '01/11/2026',
            'Voucher': 'V-001'
        }])

        original = pasajeros.copy(deep=True)

        obtener_pasajeros_con_salida(
            pasajeros,
            '01/11/2026'
        )

        pd.testing.assert_frame_equal(pasajeros, original)
    def test_sumar_bebidas_vigentes(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': '2500',
                'estado': 'vigente'
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            4000
        )
        self.assertEqual(len(resultado['detalle_confirmado']), 2)

    def test_excluir_consumos_anulados(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'habitacion': '104',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'monto': '1500',
            'estado': 'anulado'
        }])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            0
        )
        self.assertTrue(resultado['detalle_confirmado'].empty)

    def test_separar_consumos_sin_id_estadia(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([{
            'id_estadia': '',
            'habitacion': '104',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'monto': '1500',
            'estado': 'vigente'
        }])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertTrue(resultado['detalle_confirmado'].empty)
        self.assertEqual(len(resultado['pendientes']), 1)
        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            0
        )

    def test_detectar_habitacion_inconsistente(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'habitacion': '105',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'monto': '1500',
            'estado': 'vigente'
        }])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            0
        )
        self.assertEqual(len(resultado['inconsistencias']), 1)
        
    def test_excluir_importes_invalidos(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': 'importe incorrecto',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Cerveza',
                'monto': '-2000',
                'estado': 'vigente'
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            1500
        )

        self.assertEqual(len(resultado['detalle_confirmado']), 1)
        self.assertEqual(len(resultado['inconsistencias']), 2)

    def test_excluir_importes_infinitos(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'habitacion': '104',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'monto': 'inf',
            'estado': 'vigente'
        }])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            0
        )

        self.assertEqual(len(resultado['inconsistencias']), 1)
    
    def test_excluir_estados_desconocidos(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': '2000',
                'estado': 'pendiente'
            },
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Cerveza',
                'monto': '2500',
                'estado': ''
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            1500
        )

        self.assertEqual(len(resultado['detalle_confirmado']), 1)
        self.assertEqual(len(resultado['inconsistencias']), 2)
        
        
    def test_excluir_consumos_de_otras_estadias(self):
        salidas = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'Nro. habitación': '104'
        }])

        consumos = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-002',
                'habitacion': '105',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': '2500',
                'estado': 'vigente'
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            1500
        )

        self.assertEqual(len(resultado['detalle_confirmado']), 1)
        self.assertEqual(len(resultado['inconsistencias']), 0)
        self.assertEqual(len(resultado['pendientes']), 0)
        
    def test_consumos_sin_id_solo_habitaciones_con_salida(self):
        salidas = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '104'
            },
            {
                'id_estadia': 'EST-002',
                'Nro. habitación': '105'
            }
        ])

        consumos = pd.DataFrame([
            {
                'id_estadia': '',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': '',
                'habitacion': '110',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': '2000',
                'estado': 'vigente'
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(len(resultado['pendientes']), 1)

        self.assertEqual(
            resultado['pendientes'].iloc[0]['habitacion'],
            '104'
        )

        self.assertEqual(
            sum(resultado['totales_por_estadia'].values()),
            0
        )
    
    def test_separar_consumos_de_varias_estadias_en_una_habitacion(self):
        salidas = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '104'
            },
            {
                'id_estadia': 'EST-002',
                'Nro. habitación': '104'
            }
        ])

        consumos = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Agua',
                'monto': '1500',
                'estado': 'vigente'
            },
            {
                'id_estadia': 'EST-002',
                'habitacion': '104',
                'categoria': 'Bebidas',
                'item': 'Gaseosa',
                'monto': '2500',
                'estado': 'vigente'
            }
        ])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            1500
        )

        self.assertEqual(
            resultado['totales_por_estadia']['EST-002'],
            2500
        )

        self.assertEqual(len(resultado['detalle_confirmado']), 2)
    
    def test_detectar_id_estadia_duplicado(self):
        salidas = pd.DataFrame([
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '104'
            },
            {
                'id_estadia': 'EST-001',
                'Nro. habitación': '105'
            }
        ])

        consumos = pd.DataFrame([{
            'id_estadia': 'EST-001',
            'habitacion': '104',
            'categoria': 'Bebidas',
            'item': 'Agua',
            'monto': '1500',
            'estado': 'vigente'
        }])

        resultado = vincular_consumos_bebidas(salidas, consumos)

        self.assertEqual(
            resultado['totales_por_estadia']['EST-001'],
            0
        )

        self.assertEqual(len(resultado['inconsistencias']), 1)

if __name__ == '__main__':
    unittest.main()