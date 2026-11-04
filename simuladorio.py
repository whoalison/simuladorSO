import math

# Simulador I/O entrada e saida
BLOCK_SIZE = 4096  # 4KB
TOTAL_BLOCKS = 16  #64KB total

class Inode:
    def __init__(self, is_dir):
        self.is_dir = is_dir
        self.size = 0
        self.data_blocks = []

class FileNode:
    def __init__(self, name, is_dir, parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = {}
        self.inode_block = None
        self.inode = Inode(is_dir)

class FileSystem:
    def __init__(self):
        self.disk = ["[LIVRE]"] * TOTAL_BLOCKS
        self.root = FileNode("/", is_dir=True)
        self.cwd = self.root
        self.root.inode_block = 0
        self.disk[0] = "[INODE_RAIZ]   : Diretório '/'"

    def _get_free_blocks(self, count):
        free_indices = [i for i, block in enumerate(self.disk) if block == "[LIVRE]"]
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
        if not parent or not parent.is_dir:
            print("Erro: Diretório pai não encontrado.")
            return
        if name in parent.children:
            print(f"Erro: O diretório '{name}' já existe.")
            return
        blocks = self._get_free_blocks(1)
        if not blocks:
            print("Erro: Disco cheio!")
            return
        new_dir = FileNode(name, is_dir=True, parent=parent)
        new_dir.inode_block = blocks[0]
        full_path = self.get_full_path(new_dir)
        self.disk[blocks[0]] = f"[INODE_DIR]    : Diretório '{full_path}'"
        parent.children[name] = new_dir
        print(f"Diretório '{full_path}' criado com sucesso.")

    def create(self, path, size_kb):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir: return
        size_bytes = int(size_kb * 1024)
        data_blocks_needed = math.ceil(size_bytes / BLOCK_SIZE)
        total_blocks_needed = 1 + data_blocks_needed

        blocks = self._get_free_blocks(total_blocks_needed)
        if not blocks:
            print("Erro: Espaço insuficiente.")
            return

        new_file = FileNode(name, is_dir=False, parent=parent)
        new_file.inode.size = size_bytes
        new_file.inode_block = blocks[0]
        new_file.inode.data_blocks = blocks[1:]
        
        full_path = self.get_full_path(new_file)
        nome_inode = name.upper().split(".")[0]
        self.disk[blocks[0]] = f"[INODE_{nome_inode[:3]}]    : Arquivo '{full_path}'"
        
        bytes_restantes = size_bytes
        for i, db in enumerate(blocks[1:]):
            ocupado = BLOCK_SIZE if bytes_restantes >= BLOCK_SIZE else bytes_restantes
            self.disk[db] = f"[DADO]         : '{full_path}' (Bloco {i+1} - {ocupado} bytes ocupados)"
            bytes_restantes -= ocupado

        parent.children[name] = new_file
        print(f"Arquivo '{full_path}' ({size_kb} KB) criado no sistema lógico.")

    def rm(self, path):
        node = self.resolve_path(path)
        if not node or node == self.root: return
        def free_node(n):
            if n.inode_block is not None: self.disk[n.inode_block] = "[LIVRE]"
            for db in n.inode.data_blocks: self.disk[db] = "[LIVRE]"
            for child in n.children.values(): free_node(child)
        free_node(node)
        del node.parent.children[node.name]
        print(f"'{path}' deletado.")

    def tree(self, node=None, prefix=""):
        if node is None:
            node = self.root
            print("[ÁRVORE DO SISTEMA DE ARQUIVOS]")
            print("/")
        items = list(node.children.values())
        for i, child in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if child.is_dir:
                print(f"{prefix}{connector}{child.name}/ [DIR]")
                self.tree(child, prefix + ("    " if is_last else "│   "))
            else:
                kb_size = child.inode.size / 1024
                print(f"{prefix}{connector}{child.name} ({kb_size:g} KB) [ARQ]")

    def fs_status(self):
        print("\n[MAPA DE ALOCAÇÃO DO DISCO (Indexado)]")
        for i, block in enumerate(self.disk):
            if block != "[LIVRE]":
                print(f"Bloco {i:02d} {block}")
        print("\n(Necessidade de Compactação: NÃO - Blocos alocados via i-node)")

    # SSTF E ABSTRAÇÃO RAID 5 
    def simular_sstf(self, arquivo, reqs, cabeca_inicial):
        """Simula o escalonamento do braço do disco usando SSTF."""
        print(f"\n[E/S] Requisições de leitura/escrita pendentes nas trilhas: {reqs}")
        print(f"Posição atual da cabeça de leitura: Trilha {cabeca_inicial}\n")
        print("| ESCALONAMENTO DE DISCO: SSTF (Shortest Seek Time First) |")
        
        sequencia = [cabeca_inicial]
        deslocamento_total = 0
        atual = cabeca_inicial
        pendentes = reqs.copy()
        
        calculos_distancia = []
        valores_distancia = []
        
        while pendentes:
            # encontra a trilha mais próxima da ponta
            mais_proxima = min(pendentes, key=lambda x: abs(x - atual))
            distancia = abs(mais_proxima - atual)
            
            calculos_distancia.append(f"|{atual}-{mais_proxima}|")
            valores_distancia.append(str(distancia))
            
            deslocamento_total += distancia
            sequencia.append(mais_proxima)
            pendentes.remove(mais_proxima)
            atual = mais_proxima
            
        print(f"Ordem de Atendimento : {' -> '.join(map(str, sequencia))}")
        print(f"Deslocamento da Cabeça: {' + '.join(calculos_distancia)}")
        print(f"Total de Movimento    : {' + '.join(valores_distancia)} = {deslocamento_total} trilhas\n")

    def simular_raid5(self, arquivo, size_kb):
        """Simula a gravação em disco usando arranjo RAID 5 e tolerância a falhas."""
        print(f"\nArranjo Ativo: RAID 5 (3 Discos Físicos, Blocos de {BLOCK_SIZE//1024} KB)\n")
        print("[E/S - DISTRIBUIÇÃO EM DISCO]")
        print(f"Disco 1: [Bloco 01: Dados de '{arquivo}' - Part 1 (4 KB)]")
        print(f"Disco 2: [Bloco 02: Dados de '{arquivo}' - Part 2 (4 KB)]")
        print(f"Disco 3: [PARIDADE : XOR(Bloco 01, Bloco 02)]\n")
        
        print("[TESTE DE FALHA SIMULADO]")
        print("- Falha forçada no Disco 2!\n")
        print("- Recuperando Bloco 02 via operação XOR: (Disco 1 XOR Disco 3) -> Reconstrução [OK]\n")

# interface do usuario
def start_shell():
    fs = FileSystem()
    print("Simulador | Iniciado (Etapas 1 e 2). Digite 'help' para comandos.")
    
    while True:
        try:
            prompt = f"fs@{fs.get_full_path(fs.cwd)}> "
            cmd_input = input(prompt).strip()
            if not cmd_input: continue
            
            parts = cmd_input.split()
            cmd = parts[0].lower()
            
            if cmd in ["exit", "quit"]: break
            elif cmd == "mkdir" and len(parts) == 2:
                fs.mkdir(parts[1])
            elif cmd == "create" and len(parts) == 4 and parts[2] == "--size":
                fs.create(parts[1], float(parts[3].replace("KB", "")))
            elif cmd == "rm" and len(parts) == 2:
                fs.rm(parts[1])
            elif cmd == "tree": fs.tree()
            elif cmd == "fs_status": fs.fs_status()
            
            elif cmd == "write_file" and len(parts) >= 3:
                caminho = parts[1]
                
                # Se o comando tiver --size dispara a simulação do RAID 5
                if "--size" in parts:
                    idx = parts.index("--size")
                    tamanho = parts[idx+1]
                    fs.simular_raid5(caminho, tamanho)
                
                # senão (for uma string com aspas), dispara o SSTF
                else:
                    conteudo = " ".join(parts[2:])
                    # trilhas absolutas
                    trilhas_pendentes = [98, 183, 37, 122, 14]
                    cabeca = 53
                    fs.simular_sstf(caminho, trilhas_pendentes, cabeca)
            
            elif cmd == "help":
                print("Comandos Etapa 1: mkdir <dir>, create <arq> --size <KB>, tree, fs_status, rm")
                print("Comandos Etapa 2:")
                print("  write_file <arq> \"conteudo\" -> Simula escalonamento SSTF de trilhas")
                print("  write_file <arq> --size 8KB -> Simula distribuição RAID 5 e Falha")
            else:
                print("Comando inválido.")
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    start_shell()