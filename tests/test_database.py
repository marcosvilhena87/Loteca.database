"""Testes locais sem dependências externas."""

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from loteca.database import COLUNAS, ErroValidacao, carregar, construir, data_iso, validar_linha


def exemplo(**alteracoes):
    row = dict(zip(COLUNAS, [
        "1", "segunda-feira, 18/02/2002", "1", "2", "TIME A/SP",
        "TIME B/RJ", "0", "domingo, 17/02/2002", "1", "caixa", "No",
    ]))
    row.update(alteracoes)
    return row


class TestarValidacao(unittest.TestCase):
    def test_data(self):
        self.assertEqual(data_iso("domingo, 17/02/2002"), "2002-02-17")
        self.assertIsNone(data_iso(None))
        with self.assertRaises(ErroValidacao):
            data_iso("31/02/2002")

    def test_placar_inconsistente(self):
        with self.assertRaises(ErroValidacao):
            validar_linha(exemplo(resultado_placar="X"), "amostra.csv", 2)

    def test_sorteio_valido(self):
        r = validar_linha(exemplo(sorteio="SIM", data_jogo=None), "amostra.csv", 2)
        self.assertEqual(r["sorteio"], 1)
        self.assertIsNone(r["jogado_em"])

    def test_sorteio_sem_data_versus_partida(self):
        with self.assertRaises(ErroValidacao):
            validar_linha(exemplo(data_jogo=None), "amostra.csv", 2)

    def test_duplicacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dados.csv"
            with path.open("w", encoding="utf-8", newline="") as fd:
                writer = csv.DictWriter(fd, fieldnames=COLUNAS, delimiter=";")
                writer.writeheader()
                writer.writerow(exemplo())
                writer.writerow(exemplo())
            with self.assertRaises(ErroValidacao):
                carregar(Path(tmp), exigir_600=False)

    def test_sqlite_com_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "dados.csv").open("w", encoding="utf-8", newline="") as fd:
                writer = csv.DictWriter(fd, fieldnames=COLUNAS, delimiter=";")
                writer.writeheader()
                for i in range(1, 15):
                    if i == 14:
                        writer.writerow(exemplo(jogo=str(i), gols_1="0", gols_2="0",
                                               resultado_placar="X", sorteio="SIM", data_jogo=""))
                    else:
                        writer.writerow(exemplo(jogo=str(i)))
            target = root / "saida.sqlite"
            resumo = construir(root, target, exigir_600=False)
            self.assertEqual(resumo["partidas"], 14)
            self.assertEqual(resumo["sorteios"], 1)
            with sqlite3.connect(target) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM resultados_esportivos").fetchone()[0], 13)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM resultados_sorteados").fetchone()[0], 1)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_acervo_completo_se_disponivel(self):
        origem = Path("data/raw")
        if not origem.exists():
            self.skipTest("Acervo não instalado")
        registros, fontes = carregar(origem)
        self.assertEqual((len(fontes), len(registros)), (6, 8400))
        self.assertEqual(sum(r["sorteio"] for r in registros), 47)
        self.assertEqual(sum(not r["sorteio"] for r in registros), 8353)


if __name__ == "__main__":
    unittest.main()
