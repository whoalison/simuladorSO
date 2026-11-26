# simuladorSO

Simulador interativo de Sistema Operacional desenvolvido na linguagem Python, rodando inteiramente em memória RAM com estruturas de dados reais. O projeto abrange desde a camada física de disco até o escalonamento de processos e concorrência.

### Acesso ao simulador via browser : https://simuladorso-bcc.streamlit.app/

## Descrição

### 1. Sistema de arquivos
- **Árvore Hierárquica:** Navegação e manipulação de diretórios e arquivos com caminhos absolutos e relativos.
- **Disco Físico Real em RAM:** Array de objetos DiskBlock contendo bytearray de 4 KB cada.
- **Alocação Indexada (i-node):** Elimina a fragmentação externa ao mapear blocos não contíguos via tabela de referências no i-node.
- **Diagnóstico:** Cálculo dinâmico de fragmentação interna e ocupação de blocos.

### 2. Entrada/Saída (I/O)
- **Escalonamento de Disco (SSTF):** Algoritmo *Shortest Seek Time First* dinâmico que calcula a rota de menor busca mecânica e o deslocamento total da cabeça de leitura.
- **RAID 5 Bit-a-Bit:** Distribuição de dados em bytearray, cálculo real de paridade via porta lógica XOR, simulação de falha física (zeramento de disco) e reconstrução matemática dos dados originais.

### 3. Segurança
- **Modos de Execução:** Separação entre modo superusuário e usuário, restringindo operações críticas.
- **Autenticação Segura:** Armazenamento de credenciais utilizando **SHA-256 com Salt** aleatório.
- **Controle de Acesso (ACL):** Verificação de permissões(Proprietário, Grupo e Outros) com bloqueio real de operações não autorizadas.
- **Criptografia e Auditoria (Antivírus):** Criptografia em repouso nos blocos físicos e varredura de integridade comparando o hash SHA-256 atual dos blocos contra a assinatura original.

### 4. Gerenciamento de memória híbrida
- **Área Reservada (Contígua):** Espaço fixo de 4MB para o nucleo e processos críticos, diagnóstico de fragmentação externa e rotina real de **compactação de memória**.
- **Memória Virtual (Paginação + LRU):** Alocação por demanda, Tabela de Páginas por processo, tradução de endereços, detecção de Page Faults,Swap e substituição de páginas usando o LRU (Least Recently Used).

### 5. Gerenciamento de processos
- **Ciclo de Vida e Syscalls:** Status de estados (NOVO/PRONTO/EXECUTANDO/BLOQUEADO/CONCLUÍDO) + serviço de Syscalls de I/O agendadas ou aleatórias.
- **Integração CPU + RAM:** Referências dinâmicas a páginas durante a execução com atualização da tabela de molduras e contadores LRU.
- **Exclusão Mútua (Mutex):** Simulação de concorrência entre Threads disputando uma região crítica com fila de espera real.
- **Escalonador Combinado (Prioridade + Round-Robin):** Simulação tick-a-tick com filas de prioridade, Quantum configurável e relatório completo de métricas (WT,TAT,AWT,ATT, trocas de contexto e utilização da CPU).
