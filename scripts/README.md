# Painel de contribuições

O workflow `activity.yml` consulta a API GraphQL do GitHub e atualiza
`assets/activity.svg` diariamente às **06:17 (Brasília)**. Também pode ser
executado pela aba **Actions → Atualizar painel de atividade → Run workflow**.

O gerador usa apenas a biblioteca padrão do Python 3.13 ou superior. O token
automático `GITHUB_TOKEN` é suficiente; não é necessário cadastrar um token pessoal.
O repositório precisa permitir que o workflow grave o SVG na branch.

O painel mostra o calendário retornado pelo GitHub, total de contribuições,
dias ativos, maior sequência de dias consecutivos e totais das últimas 12 semanas
(incluindo a semana atual). As cores representam os níveis de atividade do GitHub.
As animações respeitam a preferência do sistema por movimento reduzido.

Para gerar localmente com um token disponível no ambiente:

```sh
python scripts/generate_activity.py --user Lkzin0122
```

Para gerar offline, salve o objeto `contributionCalendar` da resposta GraphQL:

```sh
python scripts/generate_activity.py --input calendar.json
```

A primeira versão incluída no repositório foi gerada com dados reais do calendário
público de contribuições. Se a consulta falhar, a automação mantém o último painel
válido. O SVG fica na própria branch do README, sem depender da branch `output`.

Para validar os cálculos e o tratamento de erros:

```sh
python -m unittest discover -s scripts -p 'test_*.py'
```
