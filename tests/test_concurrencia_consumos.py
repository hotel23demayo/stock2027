import csv
import fcntl
import multiprocessing
import os
import queue
import select
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app as aplicacion
import core.cambio_habitacion as cambio_habitacion
import core.consumos as consumos
import reiniciar_datos


def _alta_proceso(ruta, identificador, iniciado, en_reemplazo, liberar, resultados, pausar):
    reemplazar = os.replace

    def reemplazo_temporal(origen, destino):
        if pausar:
            en_reemplazo.set()
            if not liberar.wait(10):
                raise TimeoutError('No se liberó la escritura de prueba')
        reemplazar(origen, destino)

    try:
        with patch.object(consumos.os, 'replace', side_effect=reemplazo_temporal):
            iniciado.set()
            resultado = consumos.agregar_consumo_detallado(
                101, 'Bebidas', 1000, identificador,
                archivo_consumos=ruta, id_estadia=identificador,
            )
        resultados.put(resultado)
    except Exception as error:
        resultados.put(repr(error))


class TestConcurrenciaConsumos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directorio = Path(self.tmp.name)
        self.archivo = self.directorio / 'consumos.csv'
        self.archivo.write_text(
            'id_consumo,id_estadia,fecha,habitacion,pasajero,categoria,monto,estado,extra\n'
            '000123,00105,01/11/2026 10:00,101,ANA,Bebidas,500,vigente,000017\n',
            encoding='utf-8',
        )
        catalogo = self.directorio / 'catalogo.csv'
        catalogo.write_text(
            'codigo,producto,categoria,sector,precio_actual\n'
            'bebida_prueba,Bebida de prueba,gaseosas,Prueba,123\n',
            encoding='utf-8',
        )
        parche = patch.object(consumos, 'RUTA_CATALOGO_PRODUCTOS', catalogo)
        parche.start()
        self.addCleanup(parche.stop)

    def leer(self):
        with self.archivo.open(encoding='utf-8', newline='') as archivo:
            return list(csv.DictReader(archivo))

    def alta_individual(self, identificador='INDIVIDUAL'):
        return consumos.agregar_consumo_detallado(
            101, 'Bebidas', 1000, identificador,
            archivo_consumos=self.archivo, id_estadia=identificador,
        )

    def alta_multiple(self, identificador='MULTIPLE'):
        return consumos.agregar_consumos_bebidas_multiples(
            101,
            [{'producto_codigo': 'bebida_prueba', 'cantidad': 1,
              'pasajero': identificador, 'id_estadia': identificador}],
            self.archivo,
        )[0]

    def ejecutar_solapados(self, primero, segundo):
        esperando = threading.Event()
        liberar = threading.Event()
        inicio_segundo = threading.Event()
        fin_segundo = threading.Event()
        resultados = {}
        errores = []
        reemplazar = os.replace

        def reemplazo_temporal(origen, destino):
            if threading.current_thread().name == 'primero':
                esperando.set()
                if not liberar.wait(10):
                    raise TimeoutError('No se liberó la escritura de prueba')
            reemplazar(origen, destino)

        def ejecutar(nombre, funcion):
            try:
                if nombre == 'segundo':
                    inicio_segundo.set()
                resultados[nombre] = funcion()
            except Exception as error:
                errores.append(error)
            finally:
                if nombre == 'segundo':
                    fin_segundo.set()

        with patch.object(consumos.os, 'replace', side_effect=reemplazo_temporal):
            hilo_primero = threading.Thread(target=ejecutar, args=('primero', primero), name='primero')
            hilo_segundo = threading.Thread(target=ejecutar, args=('segundo', segundo), name='segundo')
            hilo_primero.start()
            try:
                self.assertTrue(esperando.wait(10), 'La primera escritura no alcanzó el reemplazo')
                hilo_segundo.start()
                self.assertTrue(inicio_segundo.wait(10))
                self.assertFalse(fin_segundo.wait(0.25), 'La segunda operación no esperó el bloqueo')
            finally:
                liberar.set()
                hilo_primero.join(10)
                if hilo_segundo.ident is not None:
                    hilo_segundo.join(10)
            self.assertFalse(hilo_primero.is_alive())
            self.assertFalse(hilo_segundo.is_alive())
        self.assertEqual(errores, [])
        return resultados

    def comprobar_historico(self, filas):
        anterior = next(fila for fila in filas if fila['id_consumo'] == '000123')
        self.assertEqual(anterior['id_estadia'], '00105')
        self.assertEqual(anterior['extra'], '000017')
        ids = [fila['id_consumo'] for fila in filas]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_hilos_individual_y_multiple_conservan_historial(self):
        resultados = self.ejecutar_solapados(self.alta_individual, self.alta_multiple)
        self.assertEqual(resultados, {'primero': True, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 3)
        self.comprobar_historico(filas)
        self.assertEqual({fila['id_estadia'] for fila in filas},
                         {'00105', 'INDIVIDUAL', 'MULTIPLE'})

    def test_dos_procesos_conservan_ambas_altas(self):
        contexto = multiprocessing.get_context('spawn')
        iniciado_a, iniciado_b = contexto.Event(), contexto.Event()
        esperando, liberar = contexto.Event(), contexto.Event()
        resultados = contexto.Queue()
        primero = contexto.Process(
            target=_alta_proceso,
            args=(str(self.archivo), 'PROCESO-A', iniciado_a, esperando, liberar, resultados, True),
        )
        segundo = contexto.Process(
            target=_alta_proceso,
            args=(str(self.archivo), 'PROCESO-B', iniciado_b, esperando, liberar, resultados, False),
        )
        primero.start()
        try:
            self.assertTrue(esperando.wait(15))
            segundo.start()
            self.assertTrue(iniciado_b.wait(15))
            with self.assertRaises(queue.Empty):
                resultados.get(timeout=0.5)
        finally:
            liberar.set()
            for proceso in (primero, segundo):
                if proceso.pid is not None:
                    proceso.join(15)
                    if proceso.is_alive():
                        proceso.terminate()
                        proceso.join(5)
        self.assertEqual(primero.exitcode, 0)
        self.assertEqual(segundo.exitcode, 0)
        self.assertEqual([resultados.get(timeout=5) for _ in range(2)], [True, True])
        resultados.close()
        resultados.join_thread()
        filas = self.leer()
        self.assertEqual(len(filas), 3)
        self.comprobar_historico(filas)
        self.assertEqual({fila['id_estadia'] for fila in filas},
                         {'00105', 'PROCESO-A', 'PROCESO-B'})

    def test_anulacion_y_alta_multiple_no_se_sobrescriben(self):
        resultados = self.ejecutar_solapados(
            lambda: consumos.anular_consumo_por_id(101, '000123', 'Corrección', self.archivo),
            self.alta_multiple,
        )
        self.assertEqual(resultados, {'primero': True, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 2)
        self.comprobar_historico(filas)
        self.assertEqual(filas[0]['estado'], 'anulado')
        self.assertEqual(filas[0]['motivo_anulacion'], 'Corrección')

    def test_anulacion_por_indice_y_alta_no_se_sobrescriben(self):
        resultados = self.ejecutar_solapados(
            lambda: consumos.anular_consumo_por_indice(101, 0, 'Corrección', self.archivo),
            self.alta_individual,
        )
        self.assertEqual(resultados, {'primero': True, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 2)
        self.comprobar_historico(filas)
        self.assertEqual(filas[0]['estado'], 'anulado')

    def test_migracion_de_ids_y_alta_no_se_sobrescriben(self):
        self.archivo.write_text(
            self.archivo.read_text(encoding='utf-8').replace('000123,', ',', 1),
            encoding='utf-8',
        )
        resultados = self.ejecutar_solapados(
            lambda: consumos.obtener_historial_consumos(self.archivo)['id_consumo'].iloc[0],
            self.alta_multiple,
        )
        filas = self.leer()
        self.assertEqual(len(filas), 2)
        self.assertTrue(resultados['segundo'])
        self.assertEqual(filas[0]['id_consumo'], resultados['primero'])
        self.assertEqual(filas[0]['id_estadia'], '00105')
        self.assertEqual(filas[0]['extra'], '000017')
        self.assertEqual(len({fila['id_consumo'] for fila in filas}), 2)

    def test_cambio_de_habitacion_y_alta_no_se_sobrescriben(self):
        pasajeros = self.directorio / 'pasajeros.csv'
        pd.DataFrame([{
            'Nro. habitación': '101 A', 'Apellido y nombre': 'ANA', 'id_estadia': '00105',
        }]).to_csv(pasajeros, index=False)
        with patch.object(cambio_habitacion, 'DB_PASAJEROS', str(pasajeros)), \
                patch.object(cambio_habitacion, 'DB_CONSUMOS', str(self.archivo)):
            resultados = self.ejecutar_solapados(
                lambda: cambio_habitacion.cambiar_habitacion(101, 105)[0],
                self.alta_multiple,
            )
        self.assertEqual(resultados, {'primero': True, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 2)
        self.comprobar_historico(filas)
        self.assertEqual(filas[0]['habitacion'], '105')
        self.assertEqual(filas[1]['id_estadia'], 'MULTIPLE')

    def test_cambio_parcial_y_alta_no_se_sobrescriben(self):
        pasajeros = self.directorio / 'pasajeros.csv'
        pd.DataFrame([{
            'Nro. habitación': '101 A', 'Apellido y nombre': 'ANA', 'id_estadia': '00105',
        }]).to_csv(pasajeros, index=False)
        with patch.object(cambio_habitacion, 'DB_PASAJEROS', str(pasajeros)), \
                patch.object(cambio_habitacion, 'DB_CONSUMOS', str(self.archivo)):
            resultados = self.ejecutar_solapados(
                lambda: cambio_habitacion.cambiar_pasajero_individual(101, 105, 'ANA')[0],
                self.alta_multiple,
            )
        self.assertEqual(resultados, {'primero': True, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 2)
        self.comprobar_historico(filas)
        self.assertEqual(filas[0]['habitacion'], '105')

    def test_reinicio_temporal_espera_alta_y_respalda_registros(self):
        archivo = self.directorio / reiniciar_datos.ARCHIVO_CONSUMOS
        self.archivo.rename(archivo)
        self.archivo = archivo
        resultados = self.ejecutar_solapados(
            self.alta_multiple,
            lambda: reiniciar_datos.reiniciar(self.directorio, mantener_pasajeros=True),
        )
        self.assertTrue(resultados['primero'])
        _, backup = resultados['segundo']
        with (backup / archivo.name).open(encoding='utf-8', newline='') as fuente:
            filas_backup = list(csv.DictReader(fuente))
        self.assertEqual(len(filas_backup), 2)
        self.comprobar_historico(filas_backup)
        with archivo.open(encoding='utf-8', newline='') as fuente:
            lector = csv.DictReader(fuente)
            self.assertIn('extra', lector.fieldnames)
            self.assertEqual(list(lector), [])

    def test_error_de_escritura_libera_bloqueo(self):
        original = self.archivo.read_bytes()
        with patch.object(consumos.os, 'replace', side_effect=OSError('disco')):
            self.assertFalse(self.alta_multiple())
        self.assertEqual(self.archivo.read_bytes(), original)
        with Path(str(self.archivo) + '.lock').open('a') as candado:
            fcntl.flock(candado.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(candado.fileno(), fcntl.LOCK_UN)
        self.assertTrue(self.alta_individual())
        self.comprobar_historico(self.leer())

    def test_bloqueo_del_script_y_python_comparten_candado(self):
        datos = self.directorio / 'data'
        datos.mkdir()
        (datos / 'consumos_diarios.csv').symlink_to(self.archivo)
        script = (Path(__file__).resolve().parent.parent / 'cambiar_temporada.sh').read_text(encoding='utf-8')
        cuerpo = script.split('adquirir_bloqueo_consumos() {', 1)[1].split('\n}\n', 1)[0]
        comando = (
            'adquirir_bloqueo_consumos() {' + cuerpo + '\n}\n'
            "printf 'listo\\n'\n"
            "read -r inicio\n"
            "adquirir_bloqueo_consumos || exit 1\n"
            "printf 'adquirido\\n'\n"
            "read -r terminar\n"
        )
        with consumos.bloquear_consumos(self.archivo):
            proceso = subprocess.Popen(
                ['bash', '-c', comando], cwd=self.directorio,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            try:
                self.assertTrue(select.select([proceso.stdout], [], [], 10)[0])
                self.assertEqual(proceso.stdout.readline().strip(), 'listo')
                proceso.stdin.write('iniciar\n')
                proceso.stdin.flush()
                self.assertFalse(select.select([proceso.stdout], [], [], 0.25)[0])
            except BaseException:
                proceso.kill()
                proceso.communicate(timeout=10)
                raise

        try:
            self.assertTrue(select.select([proceso.stdout], [], [], 10)[0])
            self.assertEqual(proceso.stdout.readline().strip(), 'adquirido')
            with Path(str(self.archivo) + '.lock').open('a') as candado:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(candado.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            salida, error = proceso.communicate('terminar\n', timeout=10)
            self.assertEqual(proceso.returncode, 0, error)
            self.assertEqual(salida, '')
            with Path(str(self.archivo) + '.lock').open('a') as candado:
                fcntl.flock(candado.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(candado.fileno(), fcntl.LOCK_UN)
        finally:
            if proceso.poll() is None:
                proceso.kill()
                proceso.communicate(timeout=10)

    def test_vaciado_aislado_del_script_es_atomico_y_libera_bloqueo(self):
        datos = self.directorio / 'data'
        datos.mkdir()
        (datos / 'consumos_diarios.csv').symlink_to(self.archivo)
        self.archivo.chmod(0o640)
        original = self.archivo.read_bytes()
        script = (Path(__file__).resolve().parent.parent / 'cambiar_temporada.sh').read_text(encoding='utf-8')
        cuerpo = script.split('adquirir_bloqueo_consumos() {', 1)[1].split('\n}\n', 1)[0]
        vaciado = script.split('# Resetear consumos\n', 1)[1].split(
            'echo -e "${GREEN}✅ Consumos reseteados${NC}"', 1
        )[0]
        for caso in ('falla', 'existente', 'ausente'):
            with self.subTest(caso=caso):
                if caso == 'ausente':
                    self.archivo.unlink()
                reemplazo = 'mv() { return 1; }\n' if caso == 'falla' else ''
                comando = (
                    'adquirir_bloqueo_consumos() {' + cuerpo + '\n}\n'
                    + reemplazo + 'umask 027\nadquirir_bloqueo_consumos || exit 1\n' + vaciado
                )
                resultado = subprocess.run(
                    ['bash', '-c', comando], cwd=self.directorio,
                    capture_output=True, text=True, timeout=10,
                )
                if caso == 'falla':
                    self.assertNotEqual(resultado.returncode, 0)
                    self.assertEqual(self.archivo.read_bytes(), original)
                    self.assertIn('No se pudo reiniciar', resultado.stderr)
                else:
                    self.assertEqual(resultado.returncode, 0, resultado.stderr)
                    self.assertEqual(
                        self.archivo.read_text(encoding='utf-8'),
                        'fecha,habitacion,pasajero,categoria,monto\n',
                    )
                self.assertEqual(self.archivo.stat().st_mode & 0o777, 0o640)
                self.assertEqual(list(self.directorio.glob('consumos.csv.tmp.*')), [])
                with Path(str(self.archivo) + '.lock').open('a') as candado:
                    fcntl.flock(candado.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(candado.fileno(), fcntl.LOCK_UN)

    def test_ruta_cargar_y_alta_multiple_conservan_esquema_e_historial(self):
        def enviar():
            return aplicacion.app.test_client().post('/cargar', data={
                'habitacion': '101', 'categoria': 'Bebidas', 'monto': '2000',
            }).status_code

        with patch.object(aplicacion, 'DB_CONSUMOS', str(self.archivo)), \
                patch.object(aplicacion, 'validar_pasajero', return_value='ANA'):
            resultados = self.ejecutar_solapados(enviar, self.alta_multiple)
        self.assertEqual(resultados, {'primero': 302, 'segundo': True})
        filas = self.leer()
        self.assertEqual(len(filas), 3)
        self.comprobar_historico(filas)
        self.assertEqual(filas[1]['pasajero'], 'ANA')
        self.assertEqual(float(filas[1]['monto']), 2000)


if __name__ == '__main__':
    unittest.main()
