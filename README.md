# simuladorSO
Simulador interativo de Sistema de Arquivos (File System) em Python. Implementa árvore de diretórios, operações CRUD (Create, Read, Update, Delete), simulação de blocos físicos com alocação indexada e relatório de fragmentação. Projeto para a disciplina de Sistemas Operacionais.


# Simulador de Sistema de Arquivos (File System Simulator)

Este projeto é um simulador de sistema de arquivos interativo rodando inteiramente em memória RAM. 

## Features 

- **Árvore de Diretórios Hierárquica :** Suporte a caminhos absolutos e relativos, simulando a estrutura de pastas e arquivos.
- **Interface de Linha de Comando :** Terminal interativo.
- **Operações CRUD:** Criação (`mkdir`, `create`), leitura/visualização (`tree`, `fs_status`), e exclusão (`rm`) de arquivos e diretórios.
- **Simulador de Disco Físico :** O armazenamento é dividido logicamente em blocos de tamanho fixo (configurado para 4 KB por bloco, totalizando 64 KB de "disco").

##  Alocação Indexada (i-node)

Cada arquivo possui um bloco especial de índice (o i-node) que guarda os ponteiros para os blocos de dados reais. 
