
import tempfile
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook

import app as aplicacion
from core.informe_consumos import generar_consolidado_productos


class LectorTabla(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabla = False
        self.celda = None
        self.filas = []
        self.fila = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tabla = True
        elif self.tabla and tag == "tr":
            self.fila = []
        elif self.tabla and tag in ("th", "td"):
            self.celda = []

    def handle_data(self, data):
        if self.celda is not None:
            self.celda.append(data)

    def handle_endtag(self, tag):
        if self.tabla and tag in ("th", "td"):
            self.fila.append("".join(self.celda).strip())
            self.celda = None
        elif self.tabla and tag == "tr":
            self.filas.append(self.fila)
        elif tag == "table":
            self.tabla = False


class TestInformeConsumos(unittest.TestCase):

    def test_consolida_productos_y_excluye_anulados(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "consumos_prueba.csv"

            datos = [
                {
                    "fecha": "10/11/2026 10:00",
                    "categoria": "Bebidas",
                    "item": "Coca-Cola",
                    "cantidad": 2,
                    "monto": 6000,
                    "estado": "vigente",
                },
                {
                    "fecha": "11/11/2026 12:00",
                    "categoria": "Bebidas",
                    "item": "Coca-Cola",
                    "cantidad": 1,
                    "monto": 3000,
                    "estado": "vigente",
                },
                {
                    "fecha": "12/11/2026 13:00",
                    "categoria": "Bebidas",
                    "item": "Coca-Cola",
                    "cantidad": 5,
                    "monto": 15000,
                    "estado": "anulado",
                },
                {
                    "fecha": "11/11/2026 14:00",
                    "categoria": "Bebidas",
                    "item": "Ficha de Café",
                    "cantidad": 2,
                    "monto": 6000,
                    "estado": "vigente",
                },
                {
                    "fecha": "11/11/2026 15:00",
                    "categoria": "Estadía",
                    "item": "Estadía",
                    "cantidad": 1,
                    "monto": 50000,
                    "estado": "vigente",
                },
                {
                    "fecha": "20/11/2026 15:00",
                    "categoria": "Bebidas",
                    "item": "Agua sin gas",
                    "cantidad": 1,
                    "monto": 2000,
                    "estado": "vigente",
                },
            ]

            pd.DataFrame(datos).to_csv(archivo, index=False)

            resultado = generar_consolidado_productos(
                "10/11/2026",
                "12/11/2026",
                archivo,
            )

            detalle = resultado["detalle"].set_index("Producto")

            self.assertEqual(detalle.loc["Coca-Cola", "Unidades"], 3)
            self.assertEqual(
                detalle.loc["Coca-Cola", "Importe total"], 9000
            )
            self.assertEqual(
                detalle.loc["Ficha de Café", "Unidades"], 2
            )
            self.assertNotIn("Estadía", detalle.index)
            self.assertNotIn("Agua sin gas", detalle.index)

            self.assertEqual(resultado["total_unidades"], 5)
            self.assertEqual(resultado["total_importe"], 15000)

    def test_rechaza_rango_invertido(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "consumos_prueba.csv"

            with self.assertRaises(ValueError):
                generar_consolidado_productos(
                    "12/11/2026",
                    "10/11/2026",
                    archivo,
                )


class TestPresentacionInformeConsumos(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        archivo = Path(self.carpeta.name) / "consumos.csv"
        pd.DataFrame([
            {
                "fecha": "10/11/2026 10:00", "categoria": "Bebidas",
                "item": "Agua", "cantidad": 2, "monto": 9000, "estado": "vigente",
            },
            {
                "fecha": "11/11/2026 12:00", "categoria": "Bebidas",
                "item": "Café", "cantidad": 1.5, "monto": 3000, "estado": "vigente",
            },
            {
                "fecha": "11/11/2026 13:00", "categoria": "Bebidas",
                "item": "Anulado", "cantidad": 8, "monto": 8000, "estado": "anulado",
            },
            {
                "fecha": "20/11/2026 13:00", "categoria": "Bebidas",
                "item": "Fuera del período", "cantidad": 5, "monto": 5000, "estado": "vigente",
            },
        ]).to_csv(archivo, index=False)
        parche = patch.object(aplicacion, "DB_CONSUMOS", str(archivo))
        parche.start()
        self.addCleanup(parche.stop)
        self.cliente = aplicacion.app.test_client()

        crear_temporal = tempfile.NamedTemporaryFile
        parche_temporal = patch.object(
            aplicacion.tempfile, "NamedTemporaryFile",
            side_effect=lambda **kwargs: crear_temporal(dir=self.carpeta.name, **kwargs),
        )
        parche_temporal.start()
        self.addCleanup(parche_temporal.stop)

    def test_pantalla_con_rango_y_un_dia(self):
        casos = [
            ("2026-11-10", "2026-11-11", "10/11/2026 al 11/11/2026",
             [["Producto", "Unidades"], ["Agua", "2,00"], ["Café", "1,50"],
              ["Total general", "3,50"]]),
            ("2026-11-10", "2026-11-10", "10/11/2026",
             [["Producto", "Unidades"], ["Agua", "2,00"], ["Total general", "2,00"]]),
        ]
        for desde, hasta, periodo, filas in casos:
            with self.subTest(desde=desde, hasta=hasta):
                respuesta = self.cliente.post(
                    "/informe-consumos", data={"fecha_desde": desde, "fecha_hasta": hasta}
                )
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.get_data(as_text=True)
                self.assertIn("Informe consolidado de consumos", html)
                self.assertIn("Total de unidades consumidas", html)
                self.assertIn("Período seleccionado", html)
                self.assertIn(f"<strong>{periodo}</strong>", html)
                self.assertIn(filas[-1][1], html)
                self.assertIn(f'name="fecha_desde" value="{desde}"', html)
                self.assertIn(f'name="fecha_hasta" value="{hasta}"', html)
                self.assertNotIn("Importe total", html)
                self.assertNotIn("9000", html)
                lector = LectorTabla()
                lector.feed(html)
                self.assertEqual(lector.filas, filas)

    def test_excel_con_rango_un_dia_y_sin_consumos(self):
        casos = [
            ("2026-11-10", "2026-11-11", "10/11/2026 al 11/11/2026",
             [("Agua", 2), ("Café", 1.5)], 3.5),
            ("2026-11-10", "2026-11-10", "10/11/2026", [("Agua", 2)], 2),
            ("2026-11-12", "2026-11-12", "12/11/2026", [], 0),
        ]
        for desde, hasta, periodo, detalle, total in casos:
            with self.subTest(desde=desde, hasta=hasta):
                respuesta = self.cliente.post(
                    "/informe-consumos-xlsx",
                    data={"fecha_desde": desde, "fecha_hasta": hasta},
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(
                    respuesta.mimetype,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                libro = load_workbook(BytesIO(respuesta.get_data()))
                respuesta.close()
                hoja = libro["Informe de consumos"]
                self.assertEqual(hoja.max_column, 2)
                self.assertEqual(hoja["A1"].value, "INFORME CONSOLIDADO DE CONSUMOS")
                self.assertEqual(hoja["A2"].value, f"Período: {periodo}")
                self.assertEqual((hoja["A5"].value, hoja["B5"].value), ("Producto", "Unidades"))
                filas = list(hoja.iter_rows(min_row=6, max_row=6 + len(detalle), values_only=True))
                self.assertEqual(filas, detalle + [("TOTAL GENERAL", total)])
                self.assertEqual(hoja.auto_filter.ref, f"A5:B{5 + len(detalle)}")
                self.assertEqual(str(hoja.merged_cells), "A1:B1")
                libro.close()

    def test_sin_consumos_y_fechas_invalidas(self):
        respuesta = self.cliente.post(
            "/informe-consumos",
            data={"fecha_desde": "2026-11-12", "fecha_hasta": "2026-11-12"},
        )
        html = respuesta.get_data(as_text=True)
        self.assertIn("<strong>12/11/2026</strong>", html)
        self.assertIn("No se encontraron consumos", html)
        self.assertNotIn("<table>", html)
        self.assertNotIn("Importe total", html)

        for ruta in ("/informe-consumos", "/informe-consumos-xlsx"):
            for desde, hasta in (("2026-11-11", "2026-11-10"), ("invalida", "2026-11-10")):
                with self.subTest(ruta=ruta, desde=desde):
                    respuesta = self.cliente.post(
                        ruta, data={"fecha_desde": desde, "fecha_hasta": hasta},
                        follow_redirects=True,
                    )
                    self.assertNotIn("Detalle por producto", respuesta.get_data(as_text=True))
                    if ruta == "/informe-consumos":
                        self.assertIn("No se pudo generar el informe", respuesta.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
