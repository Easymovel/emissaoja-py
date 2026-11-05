"""Integração com o sandbox público (Emissor Nacional simulado). Só roda com EMISSAOJA_TEST_KEY (chave ej_test_)."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from emissaoja import BASE_SANDBOX, Emissaoja  # noqa: E402

CHAVE = os.environ.get("EMISSAOJA_TEST_KEY")


@unittest.skipUnless(CHAVE, "defina EMISSAOJA_TEST_KEY para rodar")
class SandboxTest(unittest.TestCase):
    def test_fluxo_no_sandbox(self):
        ej = Emissaoja(CHAVE, base_url=BASE_SANDBOX)
        self.assertEqual(ej.status()["motor"], "simulado")
        if ej.empresa.obter()["credencial"]["estado"] != "ativa":
            ej.empresa.conectar("11111111000191", "qualquer")
            ej.empresa.aguardar_credencial(timeout=60)
        tomador = ej.tomadores.criar("12345678000195")["tomador"]
        pedido = ej.notas.emitir(f"sdk-py-{int(time.time())}", tomador["tipo"], tomador["id"], 10, descricao="Teste do cliente Python")["pedido"]
        final = ej.notas.aguardar(pedido["id"], timeout=120)["pedido"]
        self.assertIn(final["estado"], ("autorizada", "recusada", "incerta"))
        if final["estado"] == "autorizada":
            self.assertTrue(ej.notas.pdf(final["nota"]["origem"], final["nota"]["id"]).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
