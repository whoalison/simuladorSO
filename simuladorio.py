import math
import random
#simulador entrada e saida IO
BLOCK_SIZE = 4096  # 4 KB
TOTAL_BLOCKS = 16  # 64 KB total


class DiskBlock:
    """Representação REAL de um bloco físico no disco."""
    def __init__(self):
        self.is_free = True
        self.type = None           
        self.data = bytearray(BLOCK_SIZE) #Os bytes reais na RAM
        self.used_bytes = 0        #Quantos bytes estão preenchidos neste bloco
        self.references = []       #Para Inodes apontarem aos blocos de dados
        self.metadata_name = ""    #Nome lógico para visualização rápida

class FileNode:
    """Nó lógico para a árvore de navegação."""
    def __init__(self, name, is_dir, parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = {}
        self.inode_block_idx = -1
        self.size_bytes = 0

class FileSystem:
    def __init__(self):
        #O Disco é um array de bloco na memória RAM
        self.disk = [DiskBlock() for _ in range(TOTAL_BLOCKS)]
        
        #Raiz
        self.root = FileNode("/", is_dir=True)
        self.cwd = self.root
        
        #INODE Raiz no bloco 0
        raiz_block = self.disk[0]
        raiz_block.is_free = False
        raiz_block.type = "INODE_DIR"
        raiz_block.metadata_name = "/"
        self.root.inode_block_idx = 0

    def _get_free_blocks(self, count):
        """Busca blocos livres varrendo o estado físico das instâncias Block."""
        free_indices = [i for i, b in enumerate(self.disk) if b.is_free]
        if len(free_indices) < count: return None
        return free_indices[:count]

    def resolve_path(self, path):
        if path == "/": return self.root
        curr = self.root if path.startswith("/") else self.cwd
        parts = [p for p in path.split("/") if p not in ("", ".")]
        for p in parts:
            if p == "..":
                if curr.parent: curr = curr.parent
            elif p in curr.children:
                curr = curr.children[p]
            else:
                return None
        return curr

    def resolve_parent(self, path):
        parts = path.rsplit("/", 1)
        if len(parts) == 1: return self.cwd, parts[0]
        parent_path = parts[0] if parts[0] != "" else "/"
        return self.resolve_path(parent_path), parts[1]

    def get_full_path(self, node):
        if node == self.root: return "/"
        path = []
        while node != self.root:
            path.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(path))

    def mkdir(self, path):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir: return print("Erro: Diretório pai inválido.")
        if name in parent.children: return print("Erro: Já existe.")
        
        blocks = self._get_free_blocks(1)
        if not blocks: return print("Erro: Disco cheio!")
        
        #Lógica
        new_dir = FileNode(name, is_dir=True, parent=parent)
        new_dir.inode_block_idx = blocks[0]
        parent.children[name] = new_dir
        
        #Física
        block = self.disk[blocks[0]]
        block.is_free = False
        block.type = "INODE_DIR"
        block.metadata_name = self.get_full_path(new_dir)
        print(f"Diretório '{block.metadata_name}' criado.")

    def create(self, path, size_kb):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir: return
        
        size_bytes = int(size_kb * 1024)
        data_blocks_needed = math.ceil(size_bytes / BLOCK_SIZE)
        blocks = self._get_free_blocks(1 + data_blocks_needed)
        
        if not blocks: return print("Erro: Espaço insuficiente.")
        
        inode_idx = blocks[0]
        data_indices = blocks[1:]
        
        #Árvore
        new_file = FileNode(name, is_dir=False, parent=parent)
        new_file.size_bytes = size_bytes
        new_file.inode_block_idx = inode_idx
        parent.children[name] = new_file
        
        full_path = self.get_full_path(new_file)
        
        #i-node
        inode_block = self.disk[inode_idx]
        inode_block.is_free = False
        inode_block.type = "INODE_FILE"
        inode_block.metadata_name = full_path
        inode_block.references = data_indices
        
        #blocos de dados
        bytes_restantes = size_bytes
        for idx in data_indices:
            data_block = self.disk[idx]
            data_block.is_free = False
            data_block.type = "DATA"
            data_block.metadata_name = full_path
            
            ocupado_neste_bloco = min(BLOCK_SIZE, bytes_restantes)
            data_block.used_bytes = ocupado_neste_bloco
            #preenchendo o bytearray com o byte 'A'
            data_block.data[:ocupado_neste_bloco] = b'A' * ocupado_neste_bloco
            bytes_restantes -= ocupado_neste_bloco
            
        print(f"Arquivo '{full_path}' alocado em {1 + data_blocks_needed} blocos.")

    def rm(self, path):
        node = self.resolve_path(path)
        if not node or node == self.root: return
        
        def free_node(n):
            if n.inode_block_idx != -1:
                inode = self.disk[n.inode_block_idx]
                inode.is_free = True #Libera o bloco
                
                #Libera os blocos de dados
                for ref_idx in inode.references:
                    db = self.disk[ref_idx]
                    db.is_free = True
                    db.used_bytes = 0
                    db.data = bytearray(BLOCK_SIZE) #Zera a memoria
                    
            for child in n.children.values(): free_node(child)
            
        free_node(node)
        del node.parent.children[node.name]
        print(f"'{path}' deletado (blocos formatados e liberados).")

    def fs_status(self):
        """Lê diretamente o array de objetos físicos do disco."""
        print(f"\nTamanho do Bloco: {BLOCK_SIZE} B | Total: {TOTAL_BLOCKS} ({TOTAL_BLOCKS * BLOCK_SIZE // 1024} KB)")
        print("[MAPA DE ALOCAÇÃO FÍSICA]")
        
        frag_interna_total = 0
        
        for i, block in enumerate(self.disk):
            if block.is_free:
                print(f"Bloco {i:02d} [LIVRE]")
            elif block.type == "INODE_DIR":
                print(f"Bloco {i:02d} [INODE_DIR] : {block.metadata_name}")
            elif block.type == "INODE_FILE":
                refs = ",".join(map(str, block.references))
                print(f"Bloco {i:02d} [INODE_FILE]: {block.metadata_name} (Aponta p/ blocos: {refs})")
            elif block.type == "DATA":
                print(f"Bloco {i:02d} [DADO]      : {block.metadata_name} ({block.used_bytes} bytes ocupados)")
                desperdicio = BLOCK_SIZE - block.used_bytes
                frag_interna_total += desperdicio

        print("\n--- DIAGNÓSTICO DE FRAGMENTAÇÃO ---")
        print(f"Fragmentação Interna (Desperdício): {frag_interna_total} bytes")
        print("Fragmentação Externa: 0 bytes (Tabela i-node une blocos não contíguos)")
        print("Necessidade de Compactação: NÃO")

    def tree(self, node=None, prefix=""):
        if node is None:
            node = self.root
            print("\n[ÁRVORE DE DIRETÓRIOS]")
            print("/")
        items = list(node.children.values())
        for i, child in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if child.is_dir:
                print(f"{prefix}{connector}{child.name}/")
                self.tree(child, prefix + ("    " if is_last else "│   "))
            else:
                kb = child.size_bytes / 1024
                print(f"{prefix}{connector}{child.name} ({kb:g} KB)")

    # SSTF E RAID 5
    def simular_sstf(self, cabeca_inicial, lista_trilhas):
        """Executa o cálculo algorítmico real da fila de E/S por SSTF."""
        print(f"\n[E/S] Requisições na fila: {lista_trilhas}")
        print(f"Posição atual da cabeça de leitura: Trilha {cabeca_inicial}\n")
        print("--- ESCALONAMENTO DE DISCO: SSTF (Shortest Seek Time First) ---")
        
        pendentes = lista_trilhas.copy()
        atual = cabeca_inicial
        deslocamento_total = 0
        ordem = [atual]
        calculos = []
        
        while pendentes:
            mais_proxima = min(pendentes, key=lambda x: abs(x - atual))
            distancia = abs(mais_proxima - atual)
            
            calculos.append(f"|{atual}-{mais_proxima}|({distancia})")
            deslocamento_total += distancia
            ordem.append(mais_proxima)
            
            pendentes.remove(mais_proxima)
            atual = mais_proxima #Move a cabeça
            
        print(f"Ordem de Atendimento  : {' -> '.join(map(str, ordem))}")
        print(f"Distâncias (Passos)   : {' + '.join(calculos)}")
        print(f"Total de Movimento    : {deslocamento_total} trilhas percorridas\n")

    def simular_raid5_bit_a_bit(self, texto_dado):
        """Implementa paridade XOR em arrays de bytes para o RAID 5."""
        print(f"\n--- GRAVAÇÃO RAID 5 (Tolerância a Falhas) ---")
        print(f"Dado recebido pelo SO: '{texto_dado}'")
        
        #Transformação em bytes
        dados_bytes = bytearray(texto_dado.encode('utf-8'))
        
        #Garantir tamanho par para dividir perfeitamente em 2 discos de dados
        if len(dados_bytes) % 2 != 0:
            dados_bytes.append(0) 
            
        metade = len(dados_bytes) // 2
        parte1 = dados_bytes[:metade]
        parte2 = dados_bytes[metade:]
        
        #Discos Físicos na RAM
        disco1_data = bytearray(4096)
        disco2_data = bytearray(4096)
        disco3_paridade = bytearray(4096)
        
        #Gravação Física nos 2 primeiros discos
        disco1_data[:len(parte1)] = parte1
        disco2_data[:len(parte2)] = parte2
        
        print(f"[FISICO] Disco 1 gravou: {disco1_data[:len(parte1)]}")
        print(f"[FISICO] Disco 2 gravou: {disco2_data[:len(parte2)]}")
        
        #Cálculo do Código de Paridade (XOR: ^)
        for i in range(len(parte1)):
            disco3_paridade[i] = disco1_data[i] ^ disco2_data[i]
            
        print(f"[FISICO] Disco 3 (Paridade XOR calculada)\n")
        
        #5imulando a QUEIMA do Disco 2
        print("!!! ALERTA DE HARDWARE: DISCO 2 QUEIMOU !!!")
        disco2_data = bytearray(4096) # A memória foi zerada (perdida)
        
        #Reconstrução bit-a-bit
        print("-> Sistema RAID 5 iniciou reconstrução usando Disco 1 e Paridade (Disco 3)...")
        disco2_recuperado = bytearray(4096)
        for i in range(len(parte1)):
            disco2_recuperado[i] = disco1_data[i] ^ disco3_paridade[i]
            
        bytes_originais = disco1_data[:len(parte1)] + disco2_recuperado[:len(parte2)]
        texto_recuperado = bytes_originais.decode('utf-8').strip('\x00')
        
        print(f"[RECUPERADO] Array binário remontado: {disco2_recuperado[:len(parte2)]}")
        print(f"[SUCESSO] O dado original era: '{texto_recuperado}'\n")

def start_shell():
    fs = FileSystem()
    print("Simulador Arquitetural FS/IO. Comandos: mkdir, create, rm, tree, fs_status, sstf, raid")
    
    while True:
        try:
            cmd_input = input(f"fs@{fs.get_full_path(fs.cwd)}> ").strip()
            if not cmd_input: continue
            
            parts = cmd_input.split()
            cmd = parts[0].lower()
            
            if cmd in ["exit", "quit"]: break
            elif cmd == "mkdir" and len(parts) == 2: fs.mkdir(parts[1])
            elif cmd == "create" and len(parts) == 3: fs.create(parts[1], float(parts[2].replace("KB","")))
            elif cmd == "rm" and len(parts) == 2: fs.rm(parts[1])
            elif cmd == "tree": fs.tree()
            elif cmd == "fs_status": fs.fs_status()
            
            elif cmd == "sstf":
                #testar sstf <cabeca> <trilha1> <trilha2>...
                #testar sstf 53 98 183 37 122 14
                if len(parts) >= 3:
                    cabeca = int(parts[1])
                    trilhas = [int(x) for x in parts[2:]]
                    fs.simular_sstf(cabeca, trilhas)
                else:
                    print("Formato: sstf <cabeca_atual> <trilha1> <trilha2> ...")
                    
            elif cmd == "raid":
                texto = " ".join(parts[1:])
                if not texto: texto = "Dados confidencias da planilha CSV"
                texto = texto.replace('"', '').replace("'", "")
                fs.simular_raid5_bit_a_bit(texto)
                
            else:
                print("Comando inválido.")
        except Exception as e:
            print(f"Erro algorítmico: {e}")

if __name__ == "__main__":
    start_shell()
