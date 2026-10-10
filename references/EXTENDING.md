# Extensão para skills de sistemas específicos

Crie uma skill separada para cada produto, com documentação de schema, chaves, constraints, regras de negócio, ambientes e consultas permitidas. Faça referência à skill `mssql-database` e invoque seu executor, sem copiar credenciais para instruções nem suprimir a validação de destino e a aprovação de escrita.

Para múltiplas instâncias SQL Server use `--env-file caminho/instancia.env`. As variáveis exportadas no processo têm prioridade; evite definir globais contraditórias quando alternar ambientes. Se o arquivo de projeto estiver ausente, a skill carrega seu próprio `.env` local como fallback. Não crie esse arquivo automaticamente com senhas.
