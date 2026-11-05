# Loteca.database

Banco histórico reprodutível dos concursos **0001–0600 da Loteca** (2002–2014).

## Dados

- Seis CSVs em `data/raw/`, cada um com 100 concursos e 1.400 jogos.
- **600 concursos, 8.400 resultados**; **47 entradas com `sorteio=SIM`**, excluídas das análises esportivas.
- Origem indicada na coluna `fonte` dos dados enviados: `caixa`. A atribuição não implica conferência independente com documentos oficiais.
- Os CSVs enviados foram publicados com o mesmo conteúdo tabular e nomes simplificados (a publicação pode normalizar terminações de linha). O SQLite armazena o SHA-256 de cada arquivo publicado.

## Uso (Python 3.10+, sem dependências)

```bash
python -m loteca.database --validar-apenas
python -m loteca.database --output data/loteca.sqlite
python -m unittest discover -s tests -v
```

No SQLite:

```sql
SELECT resultado, COUNT(*) FROM resultados_esportivos GROUP BY resultado;
SELECT concurso, jogo, equipe_1, equipe_2, resultado FROM resultados_sorteados;
SELECT nome, sha256 FROM arquivos_fonte;
```

## Esquema

- `arquivos_fonte`: nome, SHA-256 e tamanho dos arquivos importados.
- `partidas`: chave primária `(concurso, jogo)`, placar e nomes originais, datas normalizadas ISO, resultado 1/X/2, marcação de sorteio e posição de origem.
- `resultados_esportivos`: apenas partidas sem sorteio.
- `resultados_sorteados`: partidas decididas por sorteio.

Validação: cabeçalho esperado, números e placares, 14 jogos por concurso, ausência de duplicatas, continuidade 1–600, faixas de cada arquivo, datas e coerência do indicador de sorteio. Erros impedem a substituição do banco de destino.

**Cuidado:** o placar 0–0 ou 1–0 em sorteios não comprova resultado esportivo; é preservado como valor original do registro. Frequências históricas são descritivas, não probabilidades calibradas para prever partidas. O projeto não oferece garantia de premiação.

## Próximas etapas

Identidade canônica dos clubes; auditoria das fontes; probabilidades pré-jogo e backtesting temporal; otimizador de fechamentos 13/14 com enumeração e robustez.

## Licença

Não definida. Verifique direitos de redistribuição e atribuição das fontes originais antes de reutilizar os dados.
