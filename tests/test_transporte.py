"""Transporte urllib: timeouts e falhas de conexão viram EmissaojaErro (sem rede: urlopen é trocado)."""

import os
import socket
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import emissaoja  # noqa: E402
from emissaoja import BASE_PRODUCAO, BASE_SANDBOX, Emissaoja, EmissaojaErro  # noqa: E402


class TransporteUrllibTest(unittest.TestCase):
    def setUp(self):
        self.ej = Emissaoja("ej_test_" + "b" * 43, base_url=BASE_SANDBOX)

    def _codigo(self, excecao):
        with mock.patch("urllib.request.urlopen", side_effect=excecao):
            with self.assertRaises(EmissaojaErro) as cm:
                self.ej.empresa.obter()
        self.assertEqual(cm.exception.status, 0)
        return cm.exception.code

    def test_timeout_de_leitura(self):
        self.assertEqual(self._codigo(socket.timeout("timed out")), "tempo_esgotado")
        self.assertEqual(self._codigo(TimeoutError("timed out")), "tempo_esgotado")

    def test_timeout_na_conexao(self):
        self.assertEqual(self._codigo(urllib.error.URLError(socket.timeout("timed out"))), "tempo_esgotado")

    def test_falhas_de_rede(self):
        self.assertEqual(self._codigo(urllib.error.URLError("Name or service not known")), "rede")
        self.assertEqual(self._codigo(ConnectionResetError("reset")), "rede")


class ConstantesTest(unittest.TestCase):
    def test_bases_e_versao(self):
        self.assertEqual(BASE_PRODUCAO, "https://emissaoja.com.br")
        self.assertEqual(BASE_SANDBOX, "https://sandbox.emissaoja.com.br")
        self.assertEqual(Emissaoja("x" * 10).base_url, BASE_PRODUCAO)
        self.assertEqual(Emissaoja("x" * 10, base_url=BASE_SANDBOX + "/").base_url, BASE_SANDBOX)
        self.assertRegex(emissaoja.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
