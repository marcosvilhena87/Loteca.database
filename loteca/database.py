"""Importação auditável de concursos históricos da Loteca (biblioteca padrão)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

COLUNAS = (
    "concurso", "data_apuracao", "jogo", "gols_1", "equipe_1",
    "equipe_2", "gols_2", "data_jogo", "resultado_placar", "fonte", "sorteio",
)
DATA_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})$")
RANGES = ((1, 100), (101, 200), (201, 300), (301, 400), (401, 500), (501, 600))


class ErroValidacao(ValueError):
    """Dado inválido ou inconsistente."""


def data_iso(valor: str | None) -> str | None:
    if valor is None or not valor.strip():
        return None
    m = DATA_PATTERN.search(valor.strip())
    if not m:
        raise ErroValidacao(f"Data inválida: {valor!r}")
    try:
        return datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
    except ValueError as exc:
        raise ErroValidacao(f"Data inválida: {valor!r}") from exc


def validar_linha(row: dict, arquivo: str, linha: int) -> dict:
    if tuple(row) != COLUNAS:
        raise ErroValidacao(f"{arquivo}:{linha}: cabeçalho inesperado: {list(row)}")
    try:
        concurso, jogo = int(row["concurso"]), int(row["jogo"])
        g1, g2 = int(row["gols_1"]), int(row["gols_2"])
    except (ValueError, TypeError) as exc:
        raise ErroValidacao(f"{arquivo}:{linha}: inteiros inválidos") from exc
    if concurso < 1 or not 1 <= jogo <= 14 or min(g1, g2) < 0:
        raise ErroValidacao(f"{arquivo}:{linha}: concurso, jogo ou gols inválidos")
    if not row["equipe_1"].strip() or not row["equipe_2"].strip() or not row["fonte"].strip():
        raise ErroValidacao(f"{arquivo}:{linha}: equipe/fonte em branco")
    resultado = "1" if g1 > g2 else ("2" if g2 > g1 else "X")
    if row["resultado_placar"] != resultado:
        raise ErroValidacao(f"{arquivo}:{linha}: placar incompatível com {row['resultado_placar']}")
    flag = row["sorteio"].strip().upper()
    if flag not in ("SIM", "NO", "NÃO", "NAO"):
        raise ErroValidacao(f"{arquivo}:{linha}: sorteio não reconhecido: {flag!r}")
    sorteio = flag == "SIM"
    jogo_em = data_iso(row["data_jogo"])
    apurado_em = data_iso(row["data_apuracao"])
    if sorteio and jogo_em is not None:
        raise ErroValidacao(f"{arquivo}:{linha}: sorteio com data de jogo")
    if not sorteio and jogo_em is None:
        raise ErroValidacao(f"{arquivo}:{linha}: jogo não sorteado sem data")
    return {
        **row,
        "concurso": concurso, "jogo": jogo,
        "apurado_em": apurado_em, "jogado_em": jogo_em,
        "gols_1": g1, "gols_2": g2, "resultado": resultado,
        "sorteio": int(sorteio),
        "arquivo_origem": arquivo, "linha_origem": linha,
    }


def carregar(diretorio: Path, exigir_600: bool = True) -> tuple[list[dict], list[tuple]]:
    arquivos = sorted(diretorio.glob("*.csv"))
    if not arquivos:
        raise ErroValidacao(f"Nenhum CSV em {diretorio}")
    registros, fontes = [], []
    vistos: set[tuple[int, int]] = set()
    for arquivo in arquivos:
        conteudo = arquivo.read_bytes()
        fontes.append((arquivo.name, hashlib.sha256(conteudo).hexdigest(), len(conteudo)))
        with arquivo.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp, delimiter=";")
            if tuple(reader.fieldnames or ()) != COLUNAS:
                raise ErroValidacao(f"{arquivo.name}: cabeçalho inválido")
            for numero_linha, row in enumerate(reader, 2):
                if None in row:
                    raise ErroValidacao(f"{arquivo.name}:{numero_linha}: colunas extras")
                item = validar_linha(row, arquivo.name, numero_linha)
                chave = (item["concurso"], item["jogo"])
                if chave in vistos:
                    raise ErroValidacao(f"Concurso/jogo duplicado: {chave}")
                vistos.add(chave)
                registros.append(item)
    contagem = Counter(r["concurso"] for r in registros)
    for concurso, quantidade in contagem.items():
        if quantidade != 14:
            raise ErroValidacao(f"Concurso {concurso}: {quantidade} partidas (esperadas: 14)")
    if exigir_600:
        if set(contagem) != set(range(1, 601)):
            raise ErroValidacao("Concursos ausentes ou extras no intervalo 0001–0600")
        if len(registros) != 8400 or len(arquivos) != 6:
            raise ErroValidacao("Esperados seis CSVs e 8.400 registros")
        for arquivo, (inicio, fim) in zip(arquivos, RANGES):
            if {r["concurso"] for r in registros if r["arquivo_origem"] == arquivo.name} != set(range(inicio, fim + 1)):
                raise ErroValidacao(f"{arquivo.name}: faixa de concursos inesperada")
    return registros, fontes


SCHEMA = """
CREATE TABLE arquivos_fonte (
    nome TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    tamanho_bytes INTEGER NOT NULL
);
CREATE TABLE partidas (
    concurso INTEGER NOT NULL CHECK (concurso >= 1),
    jogo INTEGER NOT NULL CHECK (jogo BETWEEN 1 AND 14),
    data_apuracao_original TEXT NOT NULL,
    apurado_em TEXT NOT NULL,
    equipe_1 TEXT NOT NULL,
    equipe_2 TEXT NOT NULL,
    gols_1 INTEGER NOT NULL CHECK (gols_1 >= 0),
    gols_2 INTEGER NOT NULL CHECK (gols_2 >= 0),
    data_jogo_original TEXT,
    jogado_em TEXT,
    resultado TEXT NOT NULL CHECK (resultado IN ('1', 'X', '2')),
    fonte TEXT NOT NULL,
    sorteio INTEGER NOT NULL CHECK (sorteio IN (0, 1)),
    arquivo_origem TEXT NOT NULL REFERENCES arquivos_fonte(nome),
    linha_origem INTEGER NOT NULL,
    PRIMARY KEY(concurso, jogo)
);
CREATE INDEX idx_partidas_jogado_em ON partidas(jogado_em);
CREATE INDEX idx_partidas_resultado ON partidas(resultado);
CREATE VIEW resultados_esportivos AS
SELECT * FROM partidas WHERE sorteio = 0;
CREATE VIEW resultados_sorteados AS
SELECT * FROM partidas WHERE sorteio = 1;
"""


def construir(diretorio: Path, destino: Path, exigir_600: bool = True) -> dict:
    registros, fontes = carregar(diretorio, exigir_600=exigir_600)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.unlink(missing_ok=True)
    try:
        with sqlite3.connect(temporario) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            conn.executemany(
                "INSERT INTO arquivos_fonte(nome,sha256,tamanho_bytes) VALUES (?,?,?)", fontes
            )
            conn.executemany(
                """INSERT INTO partidas (
                    concurso,jogo,data_apuracao_original,apurado_em,equipe_1,equipe_2,
                    gols_1,gols_2,data_jogo_original,jogado_em,resultado,fonte,
                    sorteio,arquivo_origem,linha_origem
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(
                    r["concurso"], r["jogo"], r["data_apuracao"], r["apurado_em"],
                    r["equipe_1"], r["equipe_2"], r["gols_1"], r["gols_2"],
                    r["data_jogo"], r["jogado_em"], r["resultado"], r["fonte"],
                    r["sorteio"], r["arquivo_origem"], r["linha_origem"],
                ) for r in registros]
            )
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ErroValidacao("Falha de integridade do SQLite")
        temporario.replace(destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    return {
        "arquivos": len(fontes), "concursos": len({r["concurso"] for r in registros}),
        "partidas": len(registros),
        "sorteios": sum(r["sorteio"] for r in registros),
        "esportivas": sum(not r["sorteio"] for r in registros),
        "sqlite": str(destino),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida e constrói o SQLite da Loteca")
    parser.add_argument("--input", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/loteca.sqlite"))
    parser.add_argument("--validar-apenas", action="store_true")
    parser.add_argument("--amostra", action="store_true", help="Não exige concursos 0001 a 0600")
    args = parser.parse_args()
    if args.validar_apenas:
        registros, fontes = carregar(args.input, exigir_600=not args.amostra)
        resultado = {"arquivos": len(fontes), "partidas": len(registros),
                     "sorteios": sum(r["sorteio"] for r in registros)}
    else:
        resultado = construir(args.input, args.output, exigir_600=not args.amostra)
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
