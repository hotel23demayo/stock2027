import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook

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
        self.assertEqual([c['monto_confirmado'] for c in cuentas[0]['detalle']], [100, 50, 200, 0])
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
        self.assertIn('Consumo de otra estadía durante el alojamiento actual', motivos)
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

    def test_clasificacion_temporal_sin_atribuir_consumos_ajenos(self):
        pasajeros = [pasajero('ACTUAL', '101', 'V1', '02/11/2026', '05/11/2026')]
        registros = []
        for identificador, fecha in (
            ('ANTERIOR', '01/11/2026 23:59'),
            ('ANTERIOR', '2026-11-01'),
            ('MISMO_DIA', '02/11/2026 10:00'),
            ('DENTRO', '03/11/2026 10:00'),
            ('EGRESO', '05/11/2026'),
            ('FUERA', '06/11/2026'),
            ('INVALIDO', 'fecha incorrecta'),
            ('VACIO', ''),
        ):
            registro = consumo(identificador)
            registro['fecha'] = fecha
            registros.append(registro)
        registros.append(consumo('ACTUAL'))
        resultado = self.generar(pasajeros, registros)
        self.assertNotIn('historicos', resultado)
        motivos = {o['registro']['id_estadia']: o['motivo'] for o in resultado['observaciones']}
        self.assertNotIn('ANTERIOR', motivos)
        for identificador in ('MISMO_DIA', 'FUERA', 'INVALIDO', 'VACIO'):
            self.assertEqual(motivos[identificador], 'Consumo de origen no verificable')
        for identificador in ('DENTRO', 'EGRESO'):
            self.assertEqual(motivos[identificador], 'Consumo de otra estadía durante el alojamiento actual')
        self.assertEqual(resultado['total_bebidas'], 100)
        self.assertEqual([c['id_estadia'] for c in resultado['cuentas'][0]['detalle']], ['ACTUAL'])

    def test_varios_ingresos_y_fechas_invalidas_se_tratan_con_cautela(self):
        registros = []
        for fecha in ('01/11/2026', '02/11/2026', '03/11/2026'):
            registro = consumo('OTRO')
            registro['fecha'] = fecha
            registros.append(registro)
        pasajeros = [
            pasajero('A', '101', 'V1', '02/11/2026', '05/11/2026'),
            pasajero('B', '101', 'V2', '01/11/2026', '05/11/2026'),
        ]
        resultado = self.generar(pasajeros, registros)
        self.assertEqual([o['motivo'] for o in resultado['observaciones']], [
            'Consumo de origen no verificable',
            'Consumo de otra estadía durante el alojamiento actual',
            'Consumo de otra estadía durante el alojamiento actual',
        ])
        pasajeros.append(pasajero('SIN_FECHA', '101', 'V3', '', '05/11/2026'))
        registros[0]['fecha'] = '31/10/2026'
        resultado = self.generar(pasajeros, registros[:1])
        self.assertIn('Consumo de origen no verificable',
                      [o['motivo'] for o in resultado['observaciones']])

    def test_historial_masivo_y_consumo_posterior_se_mantienen_separados(self):
        pasajeros = [pasajero('ACTUAL', '101', 'V1', '02/11/2026', '05/11/2026')]
        registros = []
        for i in range(542):
            registro = consumo('ANTERIOR', estado='anulado' if i == 0 else 'vigente')
            registro['id_consumo'] = str(i)
            registro['fecha'] = '01/11/2026 10:00'
            registros.append(registro)
        posterior = consumo('OTRO')
        posterior['fecha'] = '03/11/2026 10:00'
        resultado = self.generar(pasajeros, registros + [posterior])
        self.assertNotIn('historicos', resultado)
        self.assertEqual(len(resultado['observaciones']), 1)
        self.assertEqual(resultado['observaciones'][0]['registro']['id_estadia'], 'OTRO')
        self.assertEqual(resultado['total_bebidas'], 0)


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

    def test_excluye_historial_sin_observaciones_ni_modificaciones(self):
        registro = consumo('ANTERIOR')
        registro['fecha'] = '01/01/2000 10:00'
        pd.DataFrame([registro, registro]).to_csv(self.consumos, index=False)
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas')
        html = respuesta.get_data(as_text=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('Historial de estadías anteriores', html)
        self.assertNotIn('ANTERIOR', html)
        self.assertNotIn('observación(es) para revisar', html)
        self.assertIn('$ 0,00', html)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

    def test_muestra_consumo_ambiguo_sin_atribuirlo(self):
        registro = consumo('OTRO', monto='500')
        registro['fecha'] = date.today().strftime('%d/%m/%Y') + ' 10:00'
        pd.DataFrame([consumo('A'), registro]).to_csv(self.consumos, index=False)
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas')
        html = respuesta.get_data(as_text=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Consumo de origen no verificable', html)
        self.assertIn('OTRO', html)
        self.assertIn('Importe confirmado: $ 100,00', html)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

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

    def preparar_exportacion(self):
        hoy = date.today()
        ingreso = (hoy - timedelta(days=2)).strftime('%d/%m/%Y')
        egreso = (hoy + timedelta(days=2)).strftime('%d/%m/%Y')
        pasajeros = [
            pasajero('A', '101', 'V & 1', ingreso, egreso),
            pasajero('B', '101', 'V & 1', ingreso, egreso),
            pasajero('C', '101', 'V2', ingreso, egreso),
            pasajero('D', '102', 'VACIA', ingreso, egreso),
        ]
        registros = [
            consumo('A', monto='100.25', item='Agua'),
            consumo('B', monto='50', item='=Producto'),
            consumo('A', monto='900', estado='anulado', item='Anulado'),
            consumo('C', monto='300', item='Otra cuenta'),
            consumo('ANTERIOR', monto='9999', item='Histórico'),
            consumo('A', habitacion='102', monto='9999', item='Incorrecto'),
        ]
        registros[4]['fecha'] = (hoy - timedelta(days=3)).strftime('%d/%m/%Y')
        pd.DataFrame(pasajeros).to_csv(self.pasajeros, index=False)
        pd.DataFrame(registros).to_csv(self.consumos, index=False)

    def test_imprimir_cuenta_activa_no_limitada_al_checkout(self):
        self.preparar_exportacion()
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        control = self.cliente.get('/control-cuentas').get_data(as_text=True)
        self.assertIn('/control-cuentas/detalle?', control)
        self.assertIn('/control-cuentas/exportar.xlsx', control)
        respuesta = self.cliente.get('/control-cuentas/detalle', query_string={
            'habitacion': '101', 'voucher': 'V & 1',
        })
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        for texto in ('COMPROBANTE INFORMATIVO - NO FISCAL', '@page { size: A4',
                      'V &amp; 1', 'A, B', 'Agua', '=Producto', '$ 150,25',
                      'observaciones', 'Volver a Chequear Cuentas'):
            self.assertIn(texto, html)
        for texto in ('Otra cuenta', 'Histórico', 'Incorrecto', 'Anulado'):
            self.assertNotIn(texto, html)
        for query in ({}, {'habitacion': '101'}, {'habitacion': '101', 'voucher': 'NO'}):
            self.assertEqual(self.cliente.get('/control-cuentas/detalle', query_string=query).status_code, 404)
        vacia = self.cliente.get('/control-cuentas/detalle', query_string={
            'habitacion': '102', 'voucher': 'VACIA',
        }).get_data(as_text=True)
        self.assertIn('No hay bebidas confirmadas', vacia)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

    def test_excel_cuentas_actuales_detalle_y_totales(self):
        self.preparar_exportacion()
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.addCleanup(libro.close)
        detalle = libro['Detalle']
        filas = list(detalle.iter_rows(values_only=True))
        encabezados = filas[0]
        registros = [dict(zip(encabezados, fila)) for fila in filas[1:]]
        self.assertEqual([r['Producto'] for r in registros], ['Agua', '=Producto', 'Anulado', 'Otra cuenta'])
        self.assertEqual(detalle['H3'].data_type, 's')
        self.assertEqual([r['Importe confirmado'] for r in registros], [100.25, 50, 0, 300])
        self.assertEqual([r['Voucher'] for r in registros], ['V & 1', 'V & 1', 'V & 1', 'V2'])
        self.assertTrue(detalle.auto_filter.ref)
        resumen = libro['Resumen']
        filas_resumen = list(resumen.iter_rows(values_only=True))
        self.assertIn(('101', 'V & 1', 'A', 'A, B', 150.25), filas_resumen)
        self.assertIn(('101', 'V2', 'C', 'C', 300), filas_resumen)
        self.assertIn(('102', 'VACIA', 'D', 'D', 0), filas_resumen)
        self.assertIn(('TOTAL GENERAL', None, None, None, 450.25), filas_resumen)
        self.assertEqual(resumen['A3'].value, 'Hay 1 observaciones pendientes de revisión en Chequear Cuentas. Los importes confirmados pueden estar incompletos')
        for habitacion, voucher, _, _, subtotal in filas_resumen[5:-1]:
            importe = sum(
                Decimal(str(r['Importe confirmado'])) for r in registros
                if r['Habitación'] == habitacion and r['Voucher'] == voucher
            )
            self.assertEqual(importe, Decimal(str(subtotal)))
        self.assertEqual(sum(Decimal(str(r['Importe confirmado'])) for r in registros),
                         Decimal(str(filas_resumen[-1][-1])))
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

    def test_exportaciones_reportan_error_al_faltar_archivos(self):
        self.consumos.unlink()
        for ruta in ('/control-cuentas/detalle?habitacion=101&voucher=V1',
                     '/control-cuentas/exportar.xlsx'):
            respuesta = self.cliente.get(ruta)
            self.assertEqual(respuesta.status_code, 503)
            self.assertIn('No se pudo generar el control de cuentas', respuesta.get_data(as_text=True))

    def test_excel_sin_cuentas_y_cantidad_invalida_conservada(self):
        pd.DataFrame(columns=COLUMNAS_PASAJEROS).to_csv(self.pasajeros, index=False)
        respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.assertEqual(libro['Resumen']['E6'].value, 0)
        self.assertEqual(libro['Detalle'].max_row, 1)
        libro.close()

        hoy = date.today().strftime('%d/%m/%Y')
        pd.DataFrame([pasajero('A', '101', 'V1', hoy, hoy)]).to_csv(self.pasajeros, index=False)
        pd.DataFrame([consumo('A', cantidad='no válida')]).to_csv(self.consumos, index=False)
        respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.addCleanup(libro.close)
        self.assertEqual(libro['Detalle']['I2'].value, 'no válida')
        self.assertEqual(libro['Detalle']['M2'].value, 100)
        self.assertEqual(libro['Resumen']['A3'].value, 'Hay 1 observaciones pendientes de revisión en Chequear Cuentas. Los importes confirmados pueden estar incompletos')

    def test_excel_sin_observaciones_y_con_importes_invalidos_para_revision(self):
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.assertEqual(libro['Resumen']['A3'].value,
                         'Sin observaciones pendientes. Importes confirmados según los registros disponibles')
        libro.close()
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

        registros = [
            consumo('A', monto='0.1', item='Uno'),
            consumo('A', monto='0.2', item='Dos'),
            consumo('A', monto='0.3', item='Tres'),
            consumo('A', monto='no-numero', item='Inválido'),
            consumo('A', monto='nan', item='No finito'),
            consumo('A', monto='importe anulado inválido', estado='anulado', item='Anulado inválido'),
        ]
        pd.DataFrame(registros).to_csv(self.consumos, index=False)
        originales = [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)]
        respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.addCleanup(libro.close)
        filas = list(libro['Detalle'].iter_rows(min_row=2, values_only=True))
        self.assertEqual([fila[7] for fila in filas], ['Uno', 'Dos', 'Tres', 'Anulado inválido'])
        self.assertEqual(filas[-1][10], 'importe anulado inválido')
        self.assertEqual(filas[-1][12], 0)
        self.assertEqual(sum(Decimal(str(fila[12])) for fila in filas),
                         Decimal(str(libro['Resumen']['E6'].value)))
        self.assertEqual(libro['Resumen']['E6'].value, libro['Resumen']['E7'].value)
        self.assertIn('Hay 2 observaciones pendientes', libro['Resumen']['A3'].value)
        control = self.cliente.get('/control-cuentas').get_data(as_text=True)
        self.assertIn('Inválido', control)
        self.assertIn('No finito', control)
        self.assertEqual(originales, [archivo.read_bytes() for archivo in (self.pasajeros, self.consumos)])

    def test_excel_usa_importe_validado_sin_reinterpretar_monto_original(self):
        datos = aplicacion.obtener_datos_control_cuentas(date.today())
        datos['cuentas'][0]['detalle'][0]['monto'] = 'monto no interpretable'
        with patch.object(aplicacion, 'obtener_datos_control_cuentas', return_value=datos):
            respuesta = self.cliente.get('/control-cuentas/exportar.xlsx')
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.get_data()))
        self.addCleanup(libro.close)
        self.assertEqual(libro['Detalle']['K2'].value, 'monto no interpretable')
        self.assertEqual(libro['Detalle']['M2'].value, 100)
        self.assertEqual(libro['Resumen']['E6'].value, 100)


if __name__ == '__main__':
    unittest.main()
