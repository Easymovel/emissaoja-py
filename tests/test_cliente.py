"""Testes do cliente com um transporte falso (sem rede). Rodar: python -m unittest discover -s tests -v"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from emissaoja import Emissaoja, EmissaojaErro  # noqa: E402


class Transporte:
    """Guarda as chamadas e responde pelo caminho."""

    def __init__(self):
        self.chamadas = []
        self.respostas = {}

    def __call__(self, metodo, url, cabecalhos, corpo, timeout):
        self.chamadas.append((metodo, url, cabecalhos, corpo))
        caminho = url.split("emissaoja.test", 1)[1].split("?")[0]
        status, dados = self.respostas.get((metodo, caminho), (404, {"status": "ERROR", "code": "not_found", "message": "Rota não encontrada."}))
        if isinstance(dados, (bytes, bytearray)):
            return status, {"content-type": "application/pdf"}, bytes(dados)
        return status, {"content-type": "application/json", "x-request-id": "r_teste"}, json.dumps(dados).encode("utf-8")


class ClienteTest(unittest.TestCase):
    def setUp(self):
        self.t = Transporte()
        self.ej = Emissaoja("ej_live_" + "a" * 43, base_url="https://emissaoja.test", transporte=self.t)

    def test_cabecalhos_e_status_sem_chave(self):
        self.t.respostas[("GET", "/v1/status")] = (200, {"ok": True, "motor": "ok"})
        self.assertEqual(self.ej.status()["motor"], "ok")
        _, _, h, _ = self.t.chamadas[0]
        self.assertNotIn("Authorization", h)
        self.t.respostas[("GET", "/v1/empresa")] = (200, {"empresa": None})
        self.ej.empresa.obter()
        self.assertEqual(self.t.chamadas[1][2]["Authorization"], "Bearer ej_live_" + "a" * 43)
        self.assertTrue(self.t.chamadas[1][2]["User-Agent"].startswith("emissaoja-py/"))

    def test_emitir_exige_referencia_e_manda_idempotency_key(self):
        with self.assertRaises(EmissaojaErro) as cm:
            self.ej.notas.emitir("curta", "pj", "id", 10)
        self.assertEqual(cm.exception.code, "chave_idempotencia_invalida")
        self.t.respostas[("POST", "/v1/notas")] = (202, {"pedido": {"id": "p1", "estado": "na_fila"}})
        r = self.ej.notas.emitir("pedido-0001", "pj", "11111111-1111-1111-1111-111111111111", 150.0, descricao="x", competencia=None)
        self.assertEqual(r["pedido"]["id"], "p1")
        metodo, url, h, corpo = self.t.chamadas[-1]
        self.assertEqual(h["Idempotency-Key"], "pedido-0001")
        self.assertEqual(json.loads(corpo), {"tomador_tipo": "pj", "tomador_id": "11111111-1111-1111-1111-111111111111", "valor": 150.0, "descricao": "x"})

    def test_erro_da_api_vira_excecao_com_code_e_extras(self):
        self.t.respostas[("POST", "/v1/notas")] = (422, {"status": "ERROR", "code": "nota_bloqueada", "message": "Antes de emitir, resolva:", "bloqueios": [{"code": "tomador_incompleto", "mensagem": "…", "acao": "completar_tomador"}]})
        with self.assertRaises(EmissaojaErro) as cm:
            self.ej.notas.emitir("pedido-0002", "pj", "11111111-1111-1111-1111-111111111111", 10)
        e = cm.exception
        self.assertEqual((e.status, e.code, e.request_id), (422, "nota_bloqueada", "r_teste"))
        self.assertEqual(e.extras["bloqueios"][0]["acao"], "completar_tomador")

    def test_aguardar_respeita_proxima_consulta(self):
        estados = iter([{"estado": "emitindo", "proxima_consulta_ms": 1}, {"estado": "autorizada", "numero": "7"}])
        self.t.respostas[("GET", "/v1/emissoes/p1")] = (200, {})
        original = self.t.__call__

        def responder(metodo, url, h, corpo, timeout):
            status, hh, _ = original(metodo, url, h, corpo, timeout)
            return 200, hh, json.dumps({"pedido": next(estados)}).encode()

        self.ej._transporte = responder
        r = self.ej.notas.aguardar("p1", intervalo_minimo=0.001)
        self.assertEqual(r["pedido"]["numero"], "7")

    def test_query_e_bytes(self):
        self.t.respostas[("GET", "/v1/tomadores")] = (200, {"tomadores": [], "total": 0})
        self.ej.tomadores.listar(busca="alfa", pagina=2)
        self.assertIn("busca=alfa&pagina=2", self.t.chamadas[-1][1])
        self.t.respostas[("GET", "/v1/notas/local/abc/pdf")] = (200, b"%PDF-1.4 teste")
        self.assertTrue(self.ej.notas.pdf("local", "abc").startswith(b"%PDF"))
        self.t.respostas[("GET", "/v1/cnpj/11222333000181")] = (200, {"cnpj": "11222333000181"})
        self.assertEqual(self.ej.cnpj.consultar("11.222.333/0001-81")["cnpj"], "11222333000181")

    def test_dormir_injetavel_recebe_proxima_consulta(self):
        estados = iter([
            {"estado": "na_fila", "proxima_consulta_ms": 2500},
            {"estado": "emitindo", "proxima_consulta_ms": 10},
            {"estado": "recusada", "motivo_code": "E0001"},
        ])
        esperas = []
        ej = Emissaoja("ej_live_" + "a" * 43, base_url="https://emissaoja.test", transporte=lambda m, u, h, c, t: (200, {}, json.dumps({"pedido": next(estados)}).encode()), dormir=esperas.append)
        r = ej.notas.aguardar("p2")
        self.assertEqual(r["pedido"]["estado"], "recusada")
        self.assertEqual(esperas, [2.5, 1.0])

    def test_sem_chave_le_env(self):
        os.environ.pop("EMISSAOJA_KEY", None)
        ej = Emissaoja(base_url="https://emissaoja.test", transporte=self.t)
        with self.assertRaises(EmissaojaErro) as cm:
            ej.empresa.obter()
        self.assertEqual(cm.exception.code, "chave_invalida")


if __name__ == "__main__":
    unittest.main()
