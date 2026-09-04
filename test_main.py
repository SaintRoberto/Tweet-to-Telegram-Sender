import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class HistorialTests(unittest.TestCase):
    def test_un_tuit_repetido_no_se_agrega_dos_veces(self):
        enviados = {"2095681752182423771"}
        historial = ["2095681752182423771"]

        main.marcar_procesado(
            "2095681752182423771",
            enviados,
            historial
        )

        self.assertEqual(historial, ["2095681752182423771"])

    def test_historial_supera_un_escaneo_completo(self):
        with tempfile.TemporaryDirectory() as directorio:
            archivo = Path(directorio) / "last_id.txt"
            ids = [str(numero) for numero in range(1, 583)]

            main.guardar_historial(ids, archivo)

            self.assertEqual(main.cargar_historial(archivo), ids)

    def test_guardado_respeta_limite_amplio(self):
        with tempfile.TemporaryDirectory() as directorio:
            archivo = Path(directorio) / "last_id.txt"
            ids = [str(numero) for numero in range(20005)]

            with patch.object(main, "MAX_HISTORY_IDS", 20000):
                main.guardar_historial(ids, archivo)

            guardados = main.cargar_historial(archivo)
            self.assertEqual(len(guardados), 20000)
            self.assertEqual(guardados[0], "5")
            self.assertEqual(guardados[-1], "20004")


if __name__ == "__main__":
    unittest.main()
